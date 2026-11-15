"""Orchestrates publishing one message to every platform.

Design goals:

* **Isolation** – each platform runs in its own task with its own timeout and
  exception boundary. One platform failing, hanging or crashing never affects
  the others.
* **Concurrency** – platforms are independent I/O-bound calls, so they run in
  parallel; total latency is that of the slowest platform, not the sum.
* **Safe error reporting** – expected :class:`PlatformError` messages are
  returned to the caller; unexpected exceptions are logged with a traceback
  but reported generically so internals and secrets never leak.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from datetime import datetime, tzinfo

from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform
from app.platforms.exceptions import PlatformError
from app.platforms.http import PlatformHttpClient
from app.schemas import PlatformResult, PostingResponse, PostStatus

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class PostingService:
    def __init__(
        self,
        platforms: Sequence[Platform],
        *,
        timezone: tzinfo,
        platform_timeout_seconds: float,
        access_checker: PlatformHttpClient | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._platforms = tuple(platforms)
        self._timezone = timezone
        self._timeout = platform_timeout_seconds
        self._access_checker = access_checker
        self._clock: Clock = clock or (lambda: datetime.now(self._timezone))

    @property
    def platforms(self) -> tuple[Platform, ...]:
        return self._platforms

    async def publish(self, post: PostContent) -> PostingResponse:
        """Publish ``post`` everywhere and return per-platform results.

        Never raises for platform failures; results preserve registry order.
        """
        results = await asyncio.gather(*(self._publish_to(p, post) for p in self._platforms))
        response = PostingResponse.from_results(list(results))
        logger.info(
            "Posting run finished: %d/%d platforms succeeded",
            response.summary.succeeded,
            response.summary.total,
        )
        return response

    async def _publish_to(self, platform: Platform, post: PostContent) -> PlatformResult:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout):
                published = await platform.publish(post)
        except PlatformError as exc:
            return self._failed(platform, str(exc), started)
        except TimeoutError:
            return self._failed(platform, f"Timed out after {self._timeout:g}s", started)
        except Exception:
            logger.exception("Unexpected error while publishing to %s", platform.name)
            return self._failed(platform, "Internal error while publishing", started)

        # Timestamp the moment the platform confirmed the post.
        posted_at = self._clock().astimezone(self._timezone)
        public_access = await self._confirm_public_access(platform, published)
        logger.info(
            "%s: published in %.0f ms -> %s",
            platform.name,
            _elapsed_ms(started),
            published.url,
        )
        return PlatformResult(
            platform=platform.name,
            status=PostStatus.SUCCESS,
            posted_url=published.url,
            public_access=public_access,
            date=posted_at.date(),
            time=posted_at.time().replace(microsecond=0),
        )

    async def _confirm_public_access(self, platform: Platform, published: PublishedPost) -> bool:
        """Combine the platform's own claim with an anonymous HTTP probe.

        The probe can only *downgrade* a claim (e.g. a private repo); an
        inconclusive probe (network error, 5xx, rate limit) keeps the claim.
        """
        if not (published.public and published.url and self._access_checker):
            return published.public and published.url is not None
        try:
            async with asyncio.timeout(self._timeout):
                reachable = await self._access_checker.is_publicly_reachable(published.url)
        except TimeoutError:
            reachable = None
        if reachable is False:
            logger.warning("%s: %s is not publicly reachable", platform.name, published.url)
        return reachable is not False

    @staticmethod
    def _failed(platform: Platform, error: str, started: float) -> PlatformResult:
        logger.warning("%s: failed in %.0f ms – %s", platform.name, _elapsed_ms(started), error)
        return PlatformResult.failure(platform.name, error)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000
