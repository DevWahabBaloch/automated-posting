from __future__ import annotations

import asyncio
from datetime import UTC, date, time
from zoneinfo import ZoneInfo

import httpx
import respx

from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform, UnconfiguredPlatform
from app.platforms.exceptions import PlatformRequestError
from app.platforms.http import PlatformHttpClient
from app.platforms.mastodon import MastodonPlatform
from app.schemas import PostStatus
from app.services.posting_service import PostingService
from tests.conftest import FIXED_NOW, FakePlatform


def make_service(platforms: list[Platform], **kwargs: object) -> PostingService:
    options: dict[str, object] = {
        "timezone": UTC,
        "platform_timeout_seconds": 1,
        "clock": lambda: FIXED_NOW,
    }
    options.update(kwargs)
    return PostingService(platforms, **options)  # type: ignore[arg-type]


class SlowPlatform(FakePlatform):
    async def publish(self, post: PostContent) -> PublishedPost:
        await asyncio.sleep(10)
        raise AssertionError("unreachable")


async def test_one_failure_does_not_stop_other_platforms(post: PostContent) -> None:
    ok_before = FakePlatform("Before", url="https://a.example/1")
    crashing = FakePlatform("Crashing", error=RuntimeError("boom: secret-token-123"))
    rejected = FakePlatform("Rejected", error=PlatformRequestError("HTTP 422: too long"))
    ok_after = FakePlatform("After", url="https://b.example/2")

    response = await make_service([ok_before, crashing, rejected, ok_after]).publish(post)

    assert [r.platform for r in response.results] == ["Before", "Crashing", "Rejected", "After"]
    assert [r.status for r in response.results] == [
        PostStatus.SUCCESS,
        PostStatus.FAILED,
        PostStatus.FAILED,
        PostStatus.SUCCESS,
    ]
    # Unexpected exceptions are reported generically – no internals leak.
    assert response.results[1].error == "Internal error while publishing"
    assert response.results[2].error == "Request rejected: HTTP 422: too long"
    assert response.success is True
    assert response.summary.model_dump() == {"total": 4, "succeeded": 2, "failed": 2}
    assert all(p.received == [post] for p in (ok_before, crashing, rejected, ok_after))


async def test_success_result_fields(post: PostContent) -> None:
    response = await make_service([FakePlatform("A", url="https://a.example/1")]).publish(post)

    result = response.results[0]
    assert result.posted_url == "https://a.example/1"
    assert result.public_access is True
    assert result.date == date(2026, 11, 15)
    assert result.time == time(10, 30, 0)
    assert result.error is None


async def test_failure_result_fields(post: PostContent) -> None:
    unconfigured = UnconfiguredPlatform(MastodonPlatform, ["MASTODON_ACCESS_TOKEN"])

    response = await make_service([unconfigured]).publish(post)

    assert response.success is False
    assert response.results[0].model_dump() == {
        "platform": "Mastodon",
        "status": PostStatus.FAILED,
        "posted_url": None,
        "public_access": False,
        "date": None,
        "time": None,
        "error": "Platform not configured: set MASTODON_ACCESS_TOKEN",
    }


async def test_slow_platform_times_out_without_blocking_others(post: PostContent) -> None:
    service = make_service(
        [SlowPlatform("Slow"), FakePlatform("Fast")], platform_timeout_seconds=0.05
    )

    response = await asyncio.wait_for(service.publish(post), timeout=2)

    assert response.results[0].error == "Timed out after 0.05s"
    assert response.results[1].status is PostStatus.SUCCESS


async def test_platforms_run_concurrently(post: PostContent) -> None:
    class Sleepy(FakePlatform):
        async def publish(self, post: PostContent) -> PublishedPost:
            await asyncio.sleep(0.2)
            return PublishedPost(url="https://x.example", public=True)

    loop = asyncio.get_running_loop()
    started = loop.time()
    await make_service([Sleepy(f"P{i}") for i in range(5)]).publish(post)
    assert loop.time() - started < 0.6  # sequential would take >= 1.0s


async def test_posting_time_uses_configured_timezone(post: PostContent) -> None:
    service = make_service([FakePlatform("A")], timezone=ZoneInfo("Asia/Karachi"))
    result = (await service.publish(post)).results[0]
    assert (result.date, result.time) == (date(2026, 11, 15), time(15, 30, 0))


@respx.mock
async def test_public_access_probe_downgrades_unreachable_urls(post: PostContent) -> None:
    respx.get("https://public.example/1").respond(200)
    respx.get("https://private.example/1").respond(404)
    respx.get("https://flaky.example/1").mock(side_effect=httpx.ConnectError("down"))

    async with httpx.AsyncClient() as client:
        service = make_service(
            [
                FakePlatform("Public", url="https://public.example/1"),
                FakePlatform("Private", url="https://private.example/1"),
                FakePlatform("Flaky", url="https://flaky.example/1"),
                FakePlatform("MembersOnly", url="https://members.example/1", public=False),
                FakePlatform("NoUrl", url=None),
            ],
            access_checker=PlatformHttpClient(client),
        )
        results = (await service.publish(post)).results

    assert [r.public_access for r in results] == [True, False, True, False, False]
    # Members-only content is never probed.
    assert not any(c.request.url.host == "members.example" for c in respx.calls)
