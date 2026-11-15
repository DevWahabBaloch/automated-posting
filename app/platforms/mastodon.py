"""Mastodon – Post a new status.

Docs: https://docs.joinmastodon.org/methods/statuses/#create

Setup: Preferences → Development → New application (scope ``write:statuses``)
and copy the access token into ``MASTODON_ACCESS_TOKEN``.
"""

from __future__ import annotations

import uuid
from typing import Self

from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform
from app.platforms.exceptions import PlatformResponseError
from app.platforms.http import PlatformHttpClient


class MastodonPlatform(Platform):
    name = "Mastodon"
    docs_url = "https://docs.joinmastodon.org/methods/statuses/#create"
    required_settings = ("mastodon_base_url", "mastodon_access_token")

    def __init__(self, http: PlatformHttpClient, *, base_url: str, access_token: str) -> None:
        super().__init__(http)
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        assert settings.mastodon_access_token
        return cls(
            http,
            base_url=settings.mastodon_base_url,
            access_token=settings.mastodon_access_token.get_secret_value(),
        )

    async def publish(self, post: PostContent) -> PublishedPost:
        status = await self._http.request_json(
            "POST",
            f"{self._base_url}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {self._access_token}",
                # Mastodon de-duplicates requests carrying the same key, which
                # makes our connection-level retries safe.
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={"status": post.text, "visibility": "public"},
        )
        url = status.get("url") or status.get("uri")
        if not url:
            raise PlatformResponseError("url missing from Mastodon status")
        return PublishedPost(url=url, public=status.get("visibility") == "public")
