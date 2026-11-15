"""DEV Community – Forem API ``POST /api/articles``.

Docs: https://developers.forem.com/api/v1#tag/articles/operation/createArticle

Setup: https://dev.to/settings/extensions → "DEV Community API Keys".
"""

from __future__ import annotations

import re
from typing import Self

from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform
from app.platforms.exceptions import PlatformResponseError
from app.platforms.http import PlatformHttpClient

_MAX_TITLE_LENGTH = 80
_MAX_TAGS = 4  # Forem limit
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
_INVALID_TAG_CHARS = re.compile(r"[^a-z0-9]")


class DevToPlatform(Platform):
    name = "DEV Community"
    docs_url = "https://developers.forem.com/api/v1#tag/articles/operation/createArticle"
    required_settings = ("devto_api_key",)

    api_base = "https://dev.to/api"

    def __init__(self, http: PlatformHttpClient, *, api_key: str, tags: list[str]) -> None:
        super().__init__(http)
        self._api_key = api_key
        self._tags = tags

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        assert settings.devto_api_key
        return cls(
            http,
            api_key=settings.devto_api_key.get_secret_value(),
            tags=cls.normalise_tags(settings.devto_tags),
        )

    async def publish(self, post: PostContent) -> PublishedPost:
        article = await self._http.request_json(
            "POST",
            f"{self.api_base}/articles",
            headers={
                "api-key": self._api_key,
                "Accept": "application/vnd.forem.api-v1+json",
            },
            json={
                "article": {
                    "title": self.build_title(post),
                    "body_markdown": self.render_markdown(post),
                    "published": True,
                    "tags": self._tags,
                }
            },
        )
        url = article.get("url")
        if not url:
            raise PlatformResponseError("url missing from article response")
        return PublishedPost(url=url, public=bool(article.get("published", True)))

    @staticmethod
    def render_markdown(post: PostContent) -> str:
        return f"{post.text_without_link}\n\n**👉 [{post.link}]({post.link})**\n"

    @staticmethod
    def build_title(post: PostContent) -> str:
        """Use the first sentence of the message (without the link) as the title."""
        text = post.text_without_link
        title = _SENTENCE_END.split(text, maxsplit=1)[0].rstrip(" .")
        if len(title) > _MAX_TITLE_LENGTH:
            title = title[: _MAX_TITLE_LENGTH - 1].rsplit(" ", 1)[0] + "…"
        return title or "Announcement"

    @staticmethod
    def normalise_tags(raw: str) -> list[str]:
        tags: list[str] = []
        for tag in raw.split(","):
            cleaned = _INVALID_TAG_CHARS.sub("", tag.lower())
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
        return tags[:_MAX_TAGS]
