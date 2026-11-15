"""Telegram – Bot API ``sendMessage``.

Docs: https://core.telegram.org/bots/api#sendmessage

Setup: create a bot with @BotFather, create a *public* channel, add the bot as
an administrator and set ``TELEGRAM_CHAT_ID`` to ``@channel_username``.
"""

from __future__ import annotations

from typing import Any, Self

from app.config import Settings
from app.domain import PostContent, PublishedPost
from app.platforms.base import Platform
from app.platforms.exceptions import PlatformResponseError
from app.platforms.http import PlatformHttpClient

_PRIVATE_CHANNEL_PREFIX = "-100"


class TelegramPlatform(Platform):
    name = "Telegram"
    docs_url = "https://core.telegram.org/bots/api#sendmessage"
    required_settings = ("telegram_bot_token", "telegram_chat_id")

    api_base = "https://api.telegram.org"

    def __init__(self, http: PlatformHttpClient, *, bot_token: str, chat_id: str) -> None:
        super().__init__(http)
        self._bot_token = bot_token
        self._chat_id = chat_id

    @classmethod
    def from_settings(cls, settings: Settings, http: PlatformHttpClient) -> Self:
        assert settings.telegram_bot_token and settings.telegram_chat_id
        return cls(
            http,
            bot_token=settings.telegram_bot_token.get_secret_value(),
            chat_id=settings.telegram_chat_id.strip(),
        )

    async def publish(self, post: PostContent) -> PublishedPost:
        payload = await self._http.request_json(
            "POST",
            f"{self.api_base}/bot{self._bot_token}/sendMessage",
            json={
                "chat_id": self._chat_id,
                "text": post.text,
                "link_preview_options": {"url": post.link, "prefer_large_media": True},
            },
        )
        if not payload.get("ok"):
            raise PlatformResponseError(str(payload.get("description", "ok=false")))

        message: dict[str, Any] = payload.get("result") or {}
        message_id = message.get("message_id")
        if message_id is None:
            raise PlatformResponseError("message_id missing from Telegram response")
        return self._permalink(message.get("chat") or {}, int(message_id))

    @staticmethod
    def _permalink(chat: dict[str, Any], message_id: int) -> PublishedPost:
        username = chat.get("username")
        if username:
            # Public channels/supergroups have a world-readable permalink.
            return PublishedPost(url=f"https://t.me/{username}/{message_id}", public=True)

        chat_id = str(chat.get("id", ""))
        if chat_id.startswith(_PRIVATE_CHANNEL_PREFIX):
            # Private channel/supergroup: link only works for members.
            internal_id = chat_id.removeprefix(_PRIVATE_CHANNEL_PREFIX)
            return PublishedPost(url=f"https://t.me/c/{internal_id}/{message_id}", public=False)

        # Private chats and basic groups have no addressable permalink.
        return PublishedPost(url=None, public=False)
