"""Platform registry: the single place that decides *which* platforms are used.

Platform selection is internal to the application (callers only send a
message). Every registered platform is always included in the run; platforms
without credentials are represented by :class:`UnconfiguredPlatform` so the
API response tells operators exactly which environment variables to set.

To add a platform: implement :class:`~app.platforms.base.Platform` in a new
module and append the class to :data:`PLATFORM_TYPES`.
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.platforms.base import Platform, UnconfiguredPlatform
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.github_gist import GitHubGistPlatform
from app.platforms.http import PlatformHttpClient
from app.platforms.huggingface import HuggingFacePlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform

logger = logging.getLogger(__name__)

PLATFORM_TYPES: tuple[type[Platform], ...] = (
    MastodonPlatform,
    BlueskyPlatform,
    TelegramPlatform,
    DiscordPlatform,
    GitHubGistPlatform,
    DevToPlatform,
    HuggingFacePlatform,
)


def build_platforms(
    settings: Settings,
    http: PlatformHttpClient,
    platform_types: tuple[type[Platform], ...] = PLATFORM_TYPES,
) -> list[Platform]:
    """Instantiate every registered platform from settings."""
    platforms: list[Platform] = []
    for platform_cls in platform_types:
        missing = platform_cls.missing_settings(settings)
        if missing:
            logger.warning("%s disabled – missing %s", platform_cls.name, ", ".join(missing))
            platforms.append(UnconfiguredPlatform(platform_cls, missing))
            continue
        try:
            platforms.append(platform_cls.from_settings(settings, http))
        except ValueError as exc:
            logger.error("%s has invalid configuration: %s", platform_cls.name, exc)
            platforms.append(UnconfiguredPlatform(platform_cls, [f"valid settings ({exc})"]))
    configured = [p.name for p in platforms if p.configured]
    logger.info("Platforms enabled: %s", ", ".join(configured) or "none")
    return platforms
