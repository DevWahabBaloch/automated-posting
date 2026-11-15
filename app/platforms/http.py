"""Resilient HTTP transport shared by all platform adapters.

Retry policy
------------
Publishing is a **non-idempotent** operation: blindly retrying a ``POST`` that
timed out, or that returned a 5xx, risks publishing the same message twice.
Retries are therefore limited to cases where the provider provably did *not*
process the request:

* the connection could not be established (``httpx.ConnectError`` /
  ``httpx.ConnectTimeout``), and
* ``429 Too Many Requests`` (honouring ``Retry-After`` up to a cap).

Everything else fails fast and is mapped to a typed :class:`PlatformError`.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Mapping
from typing import Any

import httpx

from app.platforms.exceptions import (
    PlatformAuthError,
    PlatformRateLimitError,
    PlatformRequestError,
    PlatformResponseError,
    PlatformUnavailableError,
)

logger = logging.getLogger(__name__)

_MAX_RETRY_AFTER_SECONDS = 10.0
_MAX_ERROR_DETAIL_LENGTH = 300
_ERROR_KEYS = ("error_description", "description", "message", "error", "detail", "errors")


class PlatformHttpClient:
    """Thin wrapper around :class:`httpx.AsyncClient` adding retries and error mapping."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._client = client
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send a request and return the response, raising on any non-2xx status."""
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if attempt >= self._max_retries:
                    raise PlatformUnavailableError(f"Could not connect: {exc!s}") from exc
                await self._sleep(attempt, reason=f"connect error: {exc!s}")
            except httpx.TimeoutException as exc:
                raise PlatformUnavailableError("Request timed out") from exc
            except httpx.HTTPError as exc:
                raise PlatformUnavailableError(f"Network error: {exc!s}") from exc
            else:
                if response.status_code == 429 and attempt < self._max_retries:
                    await self._sleep(attempt, reason="HTTP 429", headers=response.headers)
                else:
                    raise_for_status(response)
                    return response
            attempt += 1

    async def request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Like :meth:`request` but decodes and returns a JSON object."""
        response = await self.request(method, url, **kwargs)
        return parse_json_object(response)

    async def is_publicly_reachable(self, url: str) -> bool | None:
        """Anonymously fetch ``url``.

        Returns ``True``/``False`` for a definitive answer and ``None`` when
        the check itself could not be completed (network failure).
        """
        try:
            response = await self._client.get(
                url,
                follow_redirects=True,
                headers={"Accept": "text/html,*/*"},
            )
        except httpx.HTTPError as exc:
            logger.warning("Public access probe failed for %s: %s", url, exc)
            return None
        if response.status_code in (401, 403, 404, 410):
            return False
        if response.is_success:
            return True
        return None  # 429/5xx etc. are inconclusive

    async def _sleep(
        self,
        attempt: int,
        *,
        reason: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        delay = _retry_after(headers) if headers else None
        if delay is None:
            # Exponential backoff with full jitter.
            delay = random.uniform(0, self._backoff_seconds * (2**attempt))  # noqa: S311 - jitter, not crypto
        logger.info("Retrying in %.2fs (attempt %d, %s)", delay, attempt + 1, reason)
        await asyncio.sleep(delay)


def raise_for_status(response: httpx.Response) -> None:
    """Map a non-2xx response onto the :class:`PlatformError` hierarchy."""
    if response.is_success:
        return

    status = response.status_code
    detail = f"HTTP {status}: {extract_error_message(response)}"
    if status in (401, 403):
        raise PlatformAuthError(detail, status_code=status)
    if status == 429:
        raise PlatformRateLimitError(detail, status_code=status)
    if 400 <= status < 500:
        raise PlatformRequestError(detail, status_code=status)
    raise PlatformUnavailableError(detail, status_code=status)


def parse_json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise PlatformResponseError("Response body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise PlatformResponseError("Expected a JSON object in the response body")
    return payload


def extract_error_message(response: httpx.Response) -> str:
    """Best-effort human-readable error from an arbitrary provider response."""
    try:
        payload: Any = response.json()
    except ValueError:
        text = response.text.strip()
        return _truncate(text) if text else (response.reason_phrase or "Unknown error")

    message = _find_message(payload)
    return _truncate(message) if message else (response.reason_phrase or "Unknown error")


def _find_message(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts = [m for item in payload if (m := _find_message(item))]
        return "; ".join(parts) or None
    if isinstance(payload, dict):
        for key in _ERROR_KEYS:
            if key in payload and (message := _find_message(payload[key])):
                return message
    return None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return min(max(float(value), 0.0), _MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        return None  # HTTP-date form: fall back to exponential backoff


def _truncate(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= _MAX_ERROR_DETAIL_LENGTH:
        return text
    return text[: _MAX_ERROR_DETAIL_LENGTH - 1] + "…"
