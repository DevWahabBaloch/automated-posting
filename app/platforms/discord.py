"""Discord – Execute Webhook.

Docs: https://discord.com/developers/docs/resources/webhook#execute-webhook

Setup: Server Settings → Integrations → Webhooks → New Webhook → copy URL into
``DISCORD_WEBHOOK_URL``. Discord messages are only visible to server members,
so ``public_access`` is reported as ``false``.
"""

from __future__ import annotations

import asyncio
from typing import Self
from urllib.parse import urlsplit

from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform
from app.platforms.exceptions import PlatformResponseError
from app.platforms.http import PlatformHttpClient

_ALLOWED_HOSTS = frozenset(
    {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"}
)


class DiscordPlatform(Platform):
    name = "Discord"
    docs_url = "https://discord.com/developers/docs/resources/webhook#execute-webhook"
    required_settings = ("discord_webhook_url",)

    def __init__(self, http: PlatformHttpClient, *, webhook_url: str) -> None:
        super().__init__(http)
        parts = urlsplit(webhook_url)
        if parts.scheme != "https" or parts.hostname not in _ALLOWED_HOSTS:
            raise ValueError("DISCORD_WEBHOOK_URL must be an https://discord.com webhook URL")
        self._webhook_url = webhook_url
        self._guild_id: str | None = None
        self._guild_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        assert settings.discord_webhook_url
        return cls(http, webhook_url=settings.discord_webhook_url.get_secret_value().strip())

    async def publish(self, post: PostContent) -> PublishedPost:
        # Resolve the guild *before* posting so a lookup failure can never turn
        # an already-published message into a reported failure.
        guild_id = await self._resolve_guild_id()
        message = await self._http.request_json(
            "POST",
            self._webhook_url,
            params={"wait": "true"},  # return the created message instead of 204
            json={
                "content": post.text,
                # Never let user input trigger @everyone / role / user pings.
                "allowed_mentions": {"parse": []},
            },
        )
        message_id, channel_id = message.get("id"), message.get("channel_id")
        if not message_id or not channel_id:
            raise PlatformResponseError("id/channel_id missing from Discord response")

        return PublishedPost(
            url=f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
            public=False,
        )

    async def _resolve_guild_id(self) -> str:
        """Look up (once) which server the webhook belongs to."""
        async with self._guild_lock:
            if self._guild_id is None:
                webhook = await self._http.request_json("GET", self._webhook_url)
                guild_id = webhook.get("guild_id")
                if not guild_id:
                    raise PlatformResponseError("guild_id missing from webhook info")
                self._guild_id = str(guild_id)
            return self._guild_id
