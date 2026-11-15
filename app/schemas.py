"""Request/response contracts for the public HTTP API."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain import PostContent
from app.utils.links import LinkValidationError, find_links, validate_url

MAX_MESSAGE_LENGTH = 200

_EXAMPLE_MESSAGE = (
    "Check out our latest business platform and grow your online visibility. https://example.com"
)


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class PostingRequest(BaseModel):
    """Body of ``POST /posting``.

    Only the message is accepted: which platforms receive it is decided by the
    application (``extra="forbid"`` rejects attempts to pass e.g. a
    ``platforms`` field).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"message": _EXAMPLE_MESSAGE}]},
    )

    message: str = Field(
        ...,
        min_length=1,
        # Enforced in the validator for a clearer message; declared for OpenAPI.
        json_schema_extra={"maxLength": MAX_MESSAGE_LENGTH},
        description=(
            f"Text to publish (max {MAX_MESSAGE_LENGTH} characters) containing "
            "exactly one http(s) call-to-action link."
        ),
    )

    @field_validator("message")
    @classmethod
    def _validate_message(cls, message: str) -> str:
        if len(message) > MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"Message must not exceed {MAX_MESSAGE_LENGTH} characters (got {len(message)})."
            )
        links = find_links(message)
        if not links:
            raise ValueError("Message must include exactly one CTA link (none found).")
        if len(links) > 1:
            found = ", ".join(link.url for link in links)
            raise ValueError(
                f"Message must include exactly one CTA link ({len(links)} found: {found})."
            )
        try:
            validate_url(links[0].url)
        except LinkValidationError as exc:
            raise ValueError(str(exc)) from exc

        remaining = message[: links[0].start] + message[links[0].start + len(links[0].url) :]
        if not remaining.strip(" \t\n.,;:!?-"):
            raise ValueError("Message must contain text in addition to the CTA link.")
        return message

    def to_content(self) -> PostContent:
        link = find_links(self.message)[0]
        return PostContent(text=self.message, link=link.url, link_start=link.start)


# --------------------------------------------------------------------------
# Response
# --------------------------------------------------------------------------
class PostStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class PlatformResult(BaseModel):
    """Outcome of publishing to one platform."""

    platform: str = Field(examples=["Mastodon"])
    status: PostStatus
    posted_url: str | None = Field(default=None, examples=["https://mastodon.social/@acme/1"])
    public_access: bool = False
    date: dt.date | None = Field(default=None, examples=["2026-11-15"])
    time: dt.time | None = Field(default=None, examples=["10:30:00"])
    error: str | None = None

    @classmethod
    def failure(cls, platform: str, error: str) -> PlatformResult:
        return cls(platform=platform, status=PostStatus.FAILED, error=error)


class PostingSummary(BaseModel):
    total: int
    succeeded: int
    failed: int


class PostingResponse(BaseModel):
    """Aggregated result of a posting run.

    ``success`` is ``true`` when the message was published to at least one
    platform; per-platform details are always in ``results``.
    """

    success: bool
    summary: PostingSummary
    results: list[PlatformResult]

    @classmethod
    def from_results(cls, results: list[PlatformResult]) -> PostingResponse:
        succeeded = sum(r.status is PostStatus.SUCCESS for r in results)
        return cls(
            success=succeeded > 0,
            summary=PostingSummary(
                total=len(results), succeeded=succeeded, failed=len(results) - succeeded
            ),
            results=results,
        )


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Uniform error envelope for every non-2xx response."""

    success: bool = False
    error: ErrorBody


class PlatformInfo(BaseModel):
    name: str
    configured: bool
    missing_settings: list[str]
    api_docs: str


class HealthResponse(BaseModel):
    status: str
    version: str
    platforms_configured: int
    platforms_total: int


def response_example() -> dict[str, Any]:
    """Example payload used in the OpenAPI docs."""
    return {
        "success": True,
        "summary": {"total": 2, "succeeded": 1, "failed": 1},
        "results": [
            {
                "platform": "Mastodon",
                "status": "success",
                "posted_url": "https://mastodon.social/@acme/113512345678901234",
                "public_access": True,
                "date": "2026-11-15",
                "time": "10:30:00",
                "error": None,
            },
            {
                "platform": "Telegram",
                "status": "failed",
                "posted_url": None,
                "public_access": False,
                "date": None,
                "time": None,
                "error": "Authentication failed: Unauthorized",
            },
        ],
    }
