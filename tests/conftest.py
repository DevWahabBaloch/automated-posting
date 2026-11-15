from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_posting_service
from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.main import create_app
from app.platforms.base import Platform
from app.platforms.exceptions import PlatformAuthError
from app.platforms.http import PlatformHttpClient
from app.schemas import PostingRequest
from app.services.posting_service import PostingService

VALID_MESSAGE = (
    "Check out our latest business platform and grow your online visibility. https://example.com"
)
FIXED_NOW = datetime(2026, 11, 15, 10, 30, 0, tzinfo=UTC)


class FakePlatform(Platform):
    """Configurable in-memory platform for service and API tests."""

    required_settings = ()

    def __init__(
        self,
        name: str,
        *,
        url: str | None = "https://example.org/post/1",
        public: bool = True,
        error: Exception | None = None,
    ) -> None:
        self.name = name  # type: ignore[misc]
        self.docs_url = "https://example.org/docs"  # type: ignore[misc]
        self._url, self._public, self._error = url, public, error
        self.received: list[PostContent] = []

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> FakePlatform:
        raise NotImplementedError

    async def publish(self, post: PostContent) -> PublishedPost:
        self.received.append(post)
        if self._error:
            raise self._error
        return PublishedPost(url=self._url, public=self._public)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    # Isolate tests from real credentials in the shell or a local .env file.
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    return Settings(_env_file=None, verify_public_access=False)  # type: ignore[call-arg]


@pytest.fixture
def post() -> PostContent:
    return PostingRequest(message=VALID_MESSAGE).to_content()


@pytest.fixture
async def http_client() -> AsyncIterator[PlatformHttpClient]:
    async with httpx.AsyncClient() as client:
        yield PlatformHttpClient(client, max_retries=2, backoff_seconds=0)


@pytest.fixture
def fake_platforms() -> list[Platform]:
    return [
        FakePlatform("Alpha", url="https://alpha.example/p/1"),
        FakePlatform("Beta", error=PlatformAuthError("HTTP 401: bad token")),
    ]


@pytest.fixture
def client(settings: Settings, fake_platforms: list[Platform]) -> Iterator[TestClient]:
    app = create_app(settings)
    service = PostingService(
        fake_platforms,
        timezone=UTC,
        platform_timeout_seconds=5,
        clock=lambda: FIXED_NOW,
    )
    app.dependency_overrides[get_posting_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
