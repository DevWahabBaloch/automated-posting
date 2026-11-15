"""FastAPI dependency providers."""

from __future__ import annotations

from fastapi import Request

from app.services.posting_service import PostingService


def get_posting_service(request: Request) -> PostingService:
    """Return the application-scoped service built during startup (see ``main.lifespan``).

    Tests replace it via ``app.dependency_overrides``.
    """
    service: PostingService = request.app.state.posting_service
    return service
