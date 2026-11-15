"""GitHub – Create a public gist.

Docs: https://docs.github.com/en/rest/gists/gists#create-a-gist

Setup: GitHub → Settings → Developer settings → Personal access tokens. A
fine-grained token needs the account permission *Gists: Read and write*; a
classic token needs the ``gist`` scope.
"""

from __future__ import annotations

from typing import Self

from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform
from app.platforms.exceptions import PlatformResponseError
from app.platforms.http import PlatformHttpClient

_MAX_DESCRIPTION_LENGTH = 120


class GitHubGistPlatform(Platform):
    name = "GitHub Gist"
    docs_url = "https://docs.github.com/en/rest/gists/gists#create-a-gist"
    required_settings = ("github_token",)

    api_base = "https://api.github.com"

    def __init__(self, http: PlatformHttpClient, *, token: str) -> None:
        super().__init__(http)
        self._token = token

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        assert settings.github_token
        return cls(http, token=settings.github_token.get_secret_value())

    async def publish(self, post: PostContent) -> PublishedPost:
        gist = await self._http.request_json(
            "POST",
            f"{self.api_base}/gists",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "description": post.text_without_link[:_MAX_DESCRIPTION_LENGTH],
                "public": True,
                "files": {"announcement.md": {"content": self.render_markdown(post)}},
            },
        )
        url = gist.get("html_url")
        if not url:
            raise PlatformResponseError("html_url missing from gist response")
        return PublishedPost(url=url, public=bool(gist.get("public")))

    @staticmethod
    def render_markdown(post: PostContent) -> str:
        return f"{post.text_without_link}\n\n👉 [{post.link}]({post.link})\n"
