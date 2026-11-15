"""HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_posting_service
from app.config import Settings, get_settings
from app.platforms.base import UnconfiguredPlatform
from app.schemas import (
    ErrorResponse,
    HealthResponse,
    PlatformInfo,
    PostingRequest,
    PostingResponse,
    response_example,
)
from app.services.posting_service import PostingService

router = APIRouter()

PostingServiceDep = Annotated[PostingService, Depends(get_posting_service)]


@router.post(
    "/posting",
    response_model=PostingResponse,
    status_code=status.HTTP_200_OK,
    tags=["Posting"],
    summary="Publish a message to all platforms",
    description=(
        "Validates the message and publishes it concurrently to every platform "
        "registered in the application. A failure on one platform never stops "
        "the others; each platform's outcome is reported in `results`. "
        "`success` is `true` when at least one platform succeeded."
    ),
    responses={
        200: {"content": {"application/json": {"example": response_example()}}},
        422: {"model": ErrorResponse, "description": "Invalid message"},
    },
)
async def create_posting(body: PostingRequest, service: PostingServiceDep) -> PostingResponse:
    return await service.publish(body.to_content())


@router.get(
    "/platforms",
    response_model=list[PlatformInfo],
    tags=["Platforms"],
    summary="List integrated platforms and their configuration status",
)
async def list_platforms(service: PostingServiceDep) -> list[PlatformInfo]:
    return [
        PlatformInfo(
            name=platform.name,
            configured=platform.configured,
            missing_settings=platform.missing if isinstance(platform, UnconfiguredPlatform) else [],
            api_docs=platform.docs_url,
        )
        for platform in service.platforms
    ]


@router.get("/health", response_model=HealthResponse, tags=["Health"], summary="Liveness check")
async def health(
    service: PostingServiceDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        platforms_configured=sum(p.configured for p in service.platforms),
        platforms_total=len(service.platforms),
    )
