"""Contract tests for each platform adapter against mocked provider APIs."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.config import Settings
from app.domain import PostContent
from app.platforms.base import UnconfiguredPlatform
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.exceptions import (
    PlatformAuthError,
    PlatformRateLimitError,
    PlatformRequestError,
    PlatformResponseError,
    PlatformUnavailableError,
)
from app.platforms.github_gist import GitHubGistPlatform
from app.platforms.http import PlatformHttpClient
from app.platforms.huggingface import HuggingFacePlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.registry import PLATFORM_TYPES, build_platforms
from app.platforms.telegram import TelegramPlatform
from app.schemas import PostingRequest


def body(call: respx.models.Call) -> dict:  # type: ignore[type-arg]
    return json.loads(call.request.content)


# --------------------------------------------------------------------------
# Shared HTTP behaviour
# --------------------------------------------------------------------------
@respx.mock
async def test_retries_rate_limit_then_succeeds(http_client: PlatformHttpClient) -> None:
    route = respx.post("https://api.example/x").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    assert await http_client.request_json("POST", "https://api.example/x") == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_retries_connection_errors(http_client: PlatformHttpClient) -> None:
    route = respx.post("https://api.example/x").mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200, json={})]
    )
    await http_client.request("POST", "https://api.example/x")
    assert route.call_count == 2


@respx.mock
async def test_does_not_retry_server_errors(http_client: PlatformHttpClient) -> None:
    """A 5xx after a POST may have been processed – retrying risks duplicates."""
    route = respx.post("https://api.example/x").respond(502, text="Bad gateway")
    with pytest.raises(PlatformUnavailableError, match="HTTP 502: Bad gateway"):
        await http_client.request("POST", "https://api.example/x")
    assert route.call_count == 1


@respx.mock
async def test_does_not_retry_read_timeouts(http_client: PlatformHttpClient) -> None:
    route = respx.post("https://api.example/x").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(PlatformUnavailableError, match="timed out"):
        await http_client.request("POST", "https://api.example/x")
    assert route.call_count == 1


@pytest.mark.parametrize(
    ("status", "payload", "exc_type", "message"),
    [
        (401, {"error": "invalid_token"}, PlatformAuthError, "HTTP 401: invalid_token"),
        (403, {"message": "Forbidden"}, PlatformAuthError, "HTTP 403: Forbidden"),
        (429, {"error": "slow down"}, PlatformRateLimitError, "HTTP 429: slow down"),
        (422, {"errors": [{"message": "a"}, {"message": "b"}]}, PlatformRequestError, "a; b"),
        (
            400,
            {"ok": False, "description": "chat not found"},
            PlatformRequestError,
            "chat not found",
        ),
    ],
)
@respx.mock
async def test_error_mapping(
    status: int,
    payload: dict,
    exc_type: type[Exception],
    message: str,  # type: ignore[type-arg]
) -> None:
    respx.post("https://api.example/x").respond(status, json=payload)
    async with httpx.AsyncClient() as client:
        http = PlatformHttpClient(client, max_retries=0)
        with pytest.raises(exc_type, match=message):
            await http.request("POST", "https://api.example/x")


@respx.mock
async def test_non_json_success_body_is_reported(http_client: PlatformHttpClient) -> None:
    respx.get("https://api.example/x").respond(200, text="<html>")
    with pytest.raises(PlatformResponseError, match="not valid JSON"):
        await http_client.request_json("GET", "https://api.example/x")


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------
def test_registry_has_at_least_five_platforms() -> None:
    assert len(PLATFORM_TYPES) >= 5
    assert len({p.name for p in PLATFORM_TYPES}) == len(PLATFORM_TYPES)


async def test_registry_builds_configured_and_placeholder_platforms(
    settings: Settings, http_client: PlatformHttpClient
) -> None:
    configured = Settings(  # type: ignore[call-arg]
        _env_file=None,
        github_token="ghp_x",
        discord_webhook_url="https://evil.example/hook",
    )

    platforms = {p.name: p for p in build_platforms(configured, http_client)}

    assert isinstance(platforms["GitHub Gist"], GitHubGistPlatform)
    discord = platforms["Discord"]
    assert isinstance(discord, UnconfiguredPlatform)  # invalid host rejected
    telegram = platforms["Telegram"]
    assert isinstance(telegram, UnconfiguredPlatform)
    assert telegram.missing == ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]


# --------------------------------------------------------------------------
# Mastodon
# --------------------------------------------------------------------------
@respx.mock
async def test_mastodon_publishes_public_status(
    http_client: PlatformHttpClient, post: PostContent
) -> None:
    route = respx.post("https://mastodon.example/api/v1/statuses").respond(
        200,
        json={"id": "1", "url": "https://mastodon.example/@acme/1", "visibility": "public"},
    )
    platform = MastodonPlatform(http_client, base_url="https://mastodon.example/", access_token="t")

    published = await platform.publish(post)

    assert (published.url, published.public) == ("https://mastodon.example/@acme/1", True)
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer t"
    assert request.headers["Idempotency-Key"]
    assert body(route.calls.last) == {"status": post.text, "visibility": "public"}


# --------------------------------------------------------------------------
# Bluesky
# --------------------------------------------------------------------------
SESSION = {"accessJwt": "jwt-1", "did": "did:plc:abc", "handle": "acme.bsky.social"}
CREATED = {"uri": "at://did:plc:abc/app.bsky.feed.post/3kxyz", "cid": "bafy"}


@respx.mock
async def test_bluesky_creates_post_with_link_facet(http_client: PlatformHttpClient) -> None:
    respx.post("https://pds.example/xrpc/com.atproto.server.createSession").respond(
        200, json=SESSION
    )
    create = respx.post("https://pds.example/xrpc/com.atproto.repo.createRecord").respond(
        200, json=CREATED
    )
    post = PostingRequest(message="Neu 🚀 für dich: https://example.com/x ok").to_content()
    platform = BlueskyPlatform(
        http_client, service_url="https://pds.example", handle="@acme.bsky.social", app_password="p"
    )

    published = await platform.publish(post)

    assert published.url == "https://bsky.app/profile/acme.bsky.social/post/3kxyz"
    payload = body(create.calls.last)
    assert payload["repo"] == "did:plc:abc"
    facet = payload["record"]["facets"][0]
    start, end = facet["index"]["byteStart"], facet["index"]["byteEnd"]
    assert post.text.encode()[start:end] == b"https://example.com/x"
    assert facet["features"][0]["uri"] == "https://example.com/x"
    assert payload["record"]["createdAt"].endswith("Z")


@respx.mock
async def test_bluesky_reuses_session_and_refreshes_when_expired(
    http_client: PlatformHttpClient, post: PostContent
) -> None:
    session = respx.post("https://pds.example/xrpc/com.atproto.server.createSession").mock(
        side_effect=[
            httpx.Response(200, json=SESSION),
            httpx.Response(200, json={**SESSION, "accessJwt": "jwt-2"}),
        ]
    )
    create = respx.post("https://pds.example/xrpc/com.atproto.repo.createRecord").mock(
        side_effect=[
            httpx.Response(200, json=CREATED),
            httpx.Response(400, json={"error": "ExpiredToken", "message": "Token has expired"}),
            httpx.Response(200, json=CREATED),
        ]
    )
    platform = BlueskyPlatform(
        http_client, service_url="https://pds.example", handle="acme.bsky.social", app_password="p"
    )

    await platform.publish(post)
    await platform.publish(post)

    assert session.call_count == 2
    assert create.calls.last.request.headers["Authorization"] == "Bearer jwt-2"


@respx.mock
async def test_bluesky_bad_credentials(http_client: PlatformHttpClient, post: PostContent) -> None:
    respx.post("https://pds.example/xrpc/com.atproto.server.createSession").respond(
        401, json={"error": "AuthenticationRequired", "message": "Invalid identifier or password"}
    )
    platform = BlueskyPlatform(
        http_client, service_url="https://pds.example", handle="a", app_password="wrong"
    )
    with pytest.raises(PlatformAuthError, match="Invalid identifier or password"):
        await platform.publish(post)


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("chat", "url", "public"),
    [
        (
            {"id": -1001234, "username": "acme_news", "type": "channel"},
            "https://t.me/acme_news/42",
            True,
        ),
        ({"id": -1001234, "type": "channel"}, "https://t.me/c/1234/42", False),
        ({"id": 555, "type": "private"}, None, False),
    ],
)
@respx.mock
async def test_telegram_permalinks(
    http_client: PlatformHttpClient,
    post: PostContent,
    chat: dict,  # type: ignore[type-arg]
    url: str | None,
    public: bool,
) -> None:
    route = respx.post("https://api.telegram.org/botTOKEN/sendMessage").respond(
        200, json={"ok": True, "result": {"message_id": 42, "chat": chat}}
    )
    platform = TelegramPlatform(http_client, bot_token="TOKEN", chat_id="@acme_news")

    published = await platform.publish(post)

    assert (published.url, published.public) == (url, public)
    assert body(route.calls.last)["chat_id"] == "@acme_news"


@respx.mock
async def test_telegram_error_description(
    http_client: PlatformHttpClient, post: PostContent
) -> None:
    respx.post("https://api.telegram.org/botBAD/sendMessage").respond(
        401, json={"ok": False, "error_code": 401, "description": "Unauthorized"}
    )
    platform = TelegramPlatform(http_client, bot_token="BAD", chat_id="@x")
    with pytest.raises(PlatformAuthError, match="Unauthorized"):
        await platform.publish(post)


# --------------------------------------------------------------------------
# Discord
# --------------------------------------------------------------------------
WEBHOOK = "https://discord.com/api/webhooks/1/secret"


@respx.mock
async def test_discord_posts_and_builds_jump_link(
    http_client: PlatformHttpClient, post: PostContent
) -> None:
    info = respx.get(WEBHOOK).respond(200, json={"guild_id": "9", "channel_id": "8"})
    execute = respx.post(WEBHOOK, params={"wait": "true"}).respond(
        200, json={"id": "7", "channel_id": "8"}
    )
    platform = DiscordPlatform(http_client, webhook_url=WEBHOOK)

    first = await platform.publish(post)
    await platform.publish(post)

    assert first.url == "https://discord.com/channels/9/8/7"
    assert first.public is False
    assert info.call_count == 1  # guild lookup is cached
    assert body(execute.calls.last)["allowed_mentions"] == {"parse": []}


def test_discord_rejects_non_discord_webhook(http_client: PlatformHttpClient) -> None:
    with pytest.raises(ValueError, match=r"discord\.com"):
        DiscordPlatform(http_client, webhook_url="https://attacker.example/api/webhooks/1/x")


# --------------------------------------------------------------------------
# GitHub Gist
# --------------------------------------------------------------------------
@respx.mock
async def test_github_gist(http_client: PlatformHttpClient, post: PostContent) -> None:
    route = respx.post("https://api.github.com/gists").respond(
        201, json={"html_url": "https://gist.github.com/acme/abc", "public": True}
    )
    published = await GitHubGistPlatform(http_client, token="ghp").publish(post)

    assert (published.url, published.public) == ("https://gist.github.com/acme/abc", True)
    payload = body(route.calls.last)
    assert payload["public"] is True
    assert "https://example.com" in payload["files"]["announcement.md"]["content"]
    assert route.calls.last.request.headers["X-GitHub-Api-Version"] == "2022-11-28"


# --------------------------------------------------------------------------
# DEV Community
# --------------------------------------------------------------------------
@respx.mock
async def test_devto_publishes_article(http_client: PlatformHttpClient, post: PostContent) -> None:
    route = respx.post("https://dev.to/api/articles").respond(
        201, json={"id": 1, "url": "https://dev.to/acme/check-out-1", "published": True}
    )
    platform = DevToPlatform(http_client, api_key="k", tags=["business"])

    published = await platform.publish(post)

    assert published.url == "https://dev.to/acme/check-out-1"
    article = body(route.calls.last)["article"]
    assert (
        article["title"] == "Check out our latest business platform and grow your online visibility"
    )
    assert article["published"] is True
    assert route.calls.last.request.headers["api-key"] == "k"


def test_devto_tags_are_normalised() -> None:
    assert DevToPlatform.normalise_tags("Business, web-dev,web-dev, A I,x,y,z") == [
        "business",
        "webdev",
        "ai",
        "x",
    ]


# --------------------------------------------------------------------------
# Hugging Face
# --------------------------------------------------------------------------
@respx.mock
async def test_huggingface_commits_post(http_client: PlatformHttpClient, post: PostContent) -> None:
    info = respx.get("https://huggingface.co/api/datasets/acme/news").respond(
        200, json={"id": "acme/news", "private": False}
    )
    commit = respx.post("https://huggingface.co/api/datasets/acme/news/commit/main").respond(
        200, json={"commitUrl": "https://huggingface.co/datasets/acme/news/commit/abc"}
    )
    platform = HuggingFacePlatform(http_client, token="hf", repo_id="acme/news")

    published = await platform.publish(post)

    assert published.public is True
    assert published.url and published.url.startswith(
        "https://huggingface.co/datasets/acme/news/blob/main/posts/"
    )
    assert info.calls.last.request.headers["Authorization"] == "Bearer hf"
    header, file_line = (
        json.loads(line) for line in commit.calls.last.request.content.splitlines()
    )
    assert header["key"] == "header"
    assert published.url.endswith(file_line["value"]["path"])
    assert post.text in base64.b64decode(file_line["value"]["content"]).decode()


@respx.mock
async def test_huggingface_private_repo_is_not_public(
    http_client: PlatformHttpClient, post: PostContent
) -> None:
    respx.get("https://huggingface.co/api/models/acme/m").respond(200, json={"private": True})
    respx.post("https://huggingface.co/api/models/acme/m/commit/main").respond(200, json={})
    platform = HuggingFacePlatform(http_client, token="hf", repo_id="acme/m", repo_type="model")

    published = await platform.publish(post)

    assert published.public is False
    assert published.url and published.url.startswith("https://huggingface.co/acme/m/blob/main/")


def test_huggingface_commit_payload_is_ndjson(post: PostContent) -> None:
    payload = HuggingFacePlatform.build_commit_payload(
        post, path="posts/a.md", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert [json.loads(line)["key"] for line in payload.splitlines()] == ["header", "file"]
