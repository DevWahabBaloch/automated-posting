"""Exception hierarchy for platform integrations.

Adapters translate every provider-specific failure into one of these types so
the posting service can report errors uniformly without knowing anything about
individual APIs.
"""

from __future__ import annotations


class PlatformError(Exception):
    """Base class for all expected, reportable platform failures."""

    prefix = "Publishing failed"

    def __init__(self, detail: str, *, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code

    def __str__(self) -> str:
        return f"{self.prefix}: {self.detail}"


class PlatformNotConfiguredError(PlatformError):
    prefix = "Platform not configured"


class PlatformAuthError(PlatformError):
    prefix = "Authentication failed"


class PlatformRateLimitError(PlatformError):
    prefix = "Rate limited"


class PlatformRequestError(PlatformError):
    """The provider rejected the request (4xx other than auth/rate limit)."""

    prefix = "Request rejected"


class PlatformUnavailableError(PlatformError):
    """Network failure or 5xx from the provider."""

    prefix = "Platform unavailable"


class PlatformResponseError(PlatformError):
    """The provider answered successfully but with an unexpected payload."""

    prefix = "Unexpected response"
