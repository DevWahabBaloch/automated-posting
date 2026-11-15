"""Exception handlers that render every error in one consistent envelope."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _error_response(status_code: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=body).model_dump(mode="json"),
    )


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registration guard
        raise exc
    details = []
    for error in exc.errors():
        # ("body", "message") -> "message"; drop the transport-level prefix.
        location = [str(part) for part in error.get("loc", ()) if part != "body"]
        message = str(error.get("msg", "Invalid value")).removeprefix("Value error, ")
        details.append(ErrorDetail(field=".".join(location) or "body", message=message))
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorBody(
            code="validation_error",
            message=details[0].message if len(details) == 1 else "Request validation failed.",
            details=details,
        ),
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover - registration guard
        raise exc
    return _error_response(
        exc.status_code,
        ErrorBody(code=f"http_{exc.status_code}", message=str(exc.detail)),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorBody(code="internal_error", message="An unexpected error occurred."),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
