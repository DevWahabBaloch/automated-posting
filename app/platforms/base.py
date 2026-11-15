"""Platform abstraction.

Every integration implements :class:`Platform`. The posting service depends
only on this interface (Dependency Inversion), and new platforms are added by
writing a new subclass and listing it in :mod:`app.platforms.registry`
(Open/Closed) – no existing code needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Self

from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.platforms.exceptions import PlatformNotConfiguredError
from app.platforms.http import PlatformHttpClient


class Platform(ABC):
    """A third-party destination that can publish a :class:`PostContent`."""

    #: Human-readable platform name used in API responses.
    name: ClassVar[str]
    #: Official API documentation consulted for the integration.
    docs_url: ClassVar[str]
    #: Settings (environment variables) that must be present for this platform.
    required_settings: ClassVar[tuple[str, ...]]

    def __init__(self, http: PlatformHttpClient) -> None:
        self._http = http

    @classmethod
    def missing_settings(cls, settings: Settings) -> list[str]:
        """Names of required environment variables that are not set."""
        missing: list[str] = []
        for field in cls.required_settings:
            value = getattr(settings, field)
            raw = value.get_secret_value() if hasattr(value, "get_secret_value") else value
            if not raw or not str(raw).strip():
                missing.append(field.upper())
        return missing

    @classmethod
    @abstractmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        """Build a configured instance. Only called when no settings are missing."""

    @property
    def configured(self) -> bool:
        return True

    @abstractmethod
    async def publish(self, post: PostContent) -> PublishedPost:
        """Publish ``post`` and return its public URL.

        Implementations must raise a :class:`~app.platforms.exceptions.PlatformError`
        subclass for every expected failure.
        """


class UnconfiguredPlatform(Platform):
    """Null-object stand-in for a platform whose credentials are missing.

    Keeping it in the platform list means the API still reports the platform
    (as failed, with an actionable error) instead of silently omitting it.
    """

    required_settings = ()

    def __init__(self, platform_cls: type[Platform], missing: list[str]) -> None:
        # No HTTP client is needed: this platform never makes a request.
        self.name = platform_cls.name  # type: ignore[misc]
        self.docs_url = platform_cls.docs_url  # type: ignore[misc]
        self.missing = missing

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        raise NotImplementedError("UnconfiguredPlatform is created by the registry")

    @property
    def configured(self) -> bool:
        return False

    async def publish(self, post: PostContent) -> PublishedPost:
        raise PlatformNotConfiguredError(f"set {', '.join(self.missing)}")
