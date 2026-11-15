"""Hugging Face Hub – commit a post to a public repository.

Hugging Face is the main public hub of the LLM/ML ecosystem. It has no
"status update" endpoint, but its Hub API lets an application commit files to
a repository; each message is committed as a Markdown file to a public dataset
repo and its permalink is returned.

Docs:
* https://huggingface.co/docs/hub/api
* https://huggingface.co/docs/huggingface_hub/guides/upload (commit API used
  by ``HfApi.create_commit``)

Setup: create a dataset repo (e.g. ``your-user/announcements``) and a token
with *write* access, then set ``HUGGINGFACE_TOKEN`` and ``HUGGINGFACE_REPO_ID``.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Self

from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform
from app.platforms.http import PlatformHttpClient

_REPO_URL_PREFIX = {"dataset": "datasets/", "space": "spaces/", "model": ""}
_BRANCH = "main"


class HuggingFacePlatform(Platform):
    name = "Hugging Face"
    docs_url = "https://huggingface.co/docs/hub/api"
    required_settings = ("huggingface_token", "huggingface_repo_id")

    hub_url = "https://huggingface.co"

    def __init__(
        self,
        http: PlatformHttpClient,
        *,
        token: str,
        repo_id: str,
        repo_type: str = "dataset",
    ) -> None:
        super().__init__(http)
        if repo_type not in _REPO_URL_PREFIX:
            raise ValueError(f"Unsupported Hugging Face repo type: {repo_type!r}")
        self._token = token
        self._repo_id = repo_id.strip("/")
        self._repo_type = repo_type

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        assert settings.huggingface_token and settings.huggingface_repo_id
        return cls(
            http,
            token=settings.huggingface_token.get_secret_value(),
            repo_id=settings.huggingface_repo_id,
            repo_type=settings.huggingface_repo_type,
        )

    async def publish(self, post: PostContent) -> PublishedPost:
        now = datetime.now(UTC)
        path = f"posts/{now:%Y/%m/%d}/{now:%H%M%S}-{uuid.uuid4().hex[:8]}.md"

        # Fetch repo metadata first: it validates the token/repo before anything
        # is written and tells us whether the content will be public.
        repo_info = await self._http.request_json(
            "GET", f"{self.hub_url}/api/{self._repo_type}s/{self._repo_id}", headers=self._auth
        )
        await self._http.request(
            "POST",
            f"{self.hub_url}/api/{self._repo_type}s/{self._repo_id}/commit/{_BRANCH}",
            headers={**self._auth, "Content-Type": "application/x-ndjson"},
            content=self.build_commit_payload(post, path=path, created_at=now),
        )
        prefix = _REPO_URL_PREFIX[self._repo_type]
        return PublishedPost(
            url=f"{self.hub_url}/{prefix}{self._repo_id}/blob/{_BRANCH}/{path}",
            public=repo_info.get("private") is False,
        )

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def build_commit_payload(post: PostContent, *, path: str, created_at: datetime) -> bytes:
        """Build the NDJSON body of a Hub commit: one header line + one file line."""
        document = (
            f"---\ncreated_at: {created_at.isoformat()}\ncta: {post.link}\n---\n\n{post.text}\n"
        )
        lines = [
            {
                "key": "header",
                "value": {"summary": f"Publish post {path}", "description": post.text},
            },
            {
                "key": "file",
                "value": {
                    "path": path,
                    "encoding": "base64",
                    "content": base64.b64encode(document.encode("utf-8")).decode("ascii"),
                },
            },
        ]
        return "\n".join(json.dumps(line, ensure_ascii=False) for line in lines).encode("utf-8")
