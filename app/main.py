"""Application entry point.

Run with::

    uvicorn app.main:app --host 0.0.0.0 --port 4000
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response

from app.api.errors import register_exception_handlers
from app.api.routes import router
from app.config import Settings, get_settings
from app.logging_config import configure_logging, request_id_var
from app.platforms.http import PlatformHttpClient
from app.platforms.registry import build_platforms
from app.services.posting_service import PostingService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory (keeps construction explicit and testable)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One pooled client for the whole process: connection reuse and
        # HTTP/1.1 keep-alive across platforms and requests.
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            headers={"User-Agent": f"automated-posting/{settings.app_version}"},
        ) as client:
            http = PlatformHttpClient(
                client,
                max_retries=settings.http_max_retries,
                backoff_seconds=settings.http_backoff_seconds,
            )
            app.state.posting_service = PostingService(
                build_platforms(settings, http),
                timezone=settings.tzinfo,
                platform_timeout_seconds=settings.platform_timeout_seconds,
                access_checker=http if settings.verify_public_access else None,
            )
            yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Publishes a short message with one call-to-action link to multiple "
            "third-party platforms (Mastodon, Bluesky, Telegram, Discord, GitHub "
            "Gist, DEV Community, Hugging Face) via their official APIs."
        ),
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(router)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %d (%.0f ms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)

    return app


app = create_app()
