"""Bluesky – AT Protocol ``com.atproto.repo.createRecord``.

Docs:
* https://docs.bsky.app/docs/advanced-guides/posts
* https://docs.bsky.app/docs/api/com-atproto-server-create-session

Setup: Settings → Privacy and security → App passwords. Put your handle in
``BLUESKY_HANDLE`` and the app password in ``BLUESKY_APP_PASSWORD``.

Bluesky does not auto-link URLs in post text; links must be declared as
rich-text *facets* addressed by UTF-8 byte offsets, which this adapter does.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform
from app.platforms.exceptions import PlatformAuthError, PlatformError, PlatformResponseError
from app.platforms.http import PlatformHttpClient

_POST_COLLECTION = "app.bsky.feed.post"


@dataclass(frozen=True, slots=True)
class _Session:
    access_jwt: str
    did: str
    handle: str


class BlueskyPlatform(Platform):
    name = "Bluesky"
    docs_url = "https://docs.bsky.app/docs/advanced-guides/posts"
    required_settings = ("bluesky_service_url", "bluesky_handle", "bluesky_app_password")

    def __init__(
        self,
        http: PlatformHttpClient,
        *,
        service_url: str,
        handle: str,
        app_password: str,
    ) -> None:
        super().__init__(http)
        self._service_url = service_url.rstrip("/")
        self._handle = handle.lstrip("@")
        self._app_password = app_password
        self._session: _Session | None = None
        self._session_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        assert settings.bluesky_handle and settings.bluesky_app_password
        return cls(
            http,
            service_url=settings.bluesky_service_url,
            handle=settings.bluesky_handle.strip(),
            app_password=settings.bluesky_app_password.get_secret_value(),
        )

    async def publish(self, post: PostContent) -> PublishedPost:
        record = self.build_record(post, created_at=datetime.now(UTC))
        session = await self._get_session()
        try:
            created = await self._create_record(session, record)
        except PlatformError as exc:
            if not _is_expired_session(exc):
                raise
            # Cached access token expired – re-authenticate once and retry.
            session = await self._get_session(force_refresh=True)
            created = await self._create_record(session, record)

        uri = created.get("uri")
        if not isinstance(uri, str) or "/" not in uri:
            raise PlatformResponseError("uri missing from createRecord response")
        record_key = uri.rsplit("/", 1)[-1]
        return PublishedPost(
            url=f"https://bsky.app/profile/{session.handle}/post/{record_key}",
            public=True,
        )

    @staticmethod
    def build_record(post: PostContent, *, created_at: datetime) -> dict[str, Any]:
        byte_start, byte_end = post.utf8_link_span()
        return {
            "$type": _POST_COLLECTION,
            "text": post.text,
            "createdAt": created_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "facets": [
                {
                    "index": {"byteStart": byte_start, "byteEnd": byte_end},
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": post.link}],
                }
            ],
        }

    async def _create_record(self, session: _Session, record: dict[str, Any]) -> dict[str, Any]:
        return await self._http.request_json(
            "POST",
            f"{self._service_url}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session.access_jwt}"},
            json={"repo": session.did, "collection": _POST_COLLECTION, "record": record},
        )

    async def _get_session(self, *, force_refresh: bool = False) -> _Session:
        # createSession is aggressively rate limited, so reuse the session
        # across requests and serialise concurrent refreshes.
        async with self._session_lock:
            if self._session is None or force_refresh:
                data = await self._http.request_json(
                    "POST",
                    f"{self._service_url}/xrpc/com.atproto.server.createSession",
                    json={"identifier": self._handle, "password": self._app_password},
                )
                try:
                    self._session = _Session(
                        access_jwt=data["accessJwt"],
                        did=data["did"],
                        handle=data.get("handle") or self._handle,
                    )
                except KeyError as exc:
                    raise PlatformResponseError(f"{exc.args[0]} missing from session") from exc
            return self._session


def _is_expired_session(exc: PlatformError) -> bool:
    # PDS implementations answer 401, or 400 with error "ExpiredToken".
    return isinstance(exc, PlatformAuthError) or "expired" in exc.detail.lower()
