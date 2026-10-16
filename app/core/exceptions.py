import logging
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        self.headers = headers
        super().__init__(message)


class ValidationError(AppError):
    def __init__(
        self,
        message: str = "Invalid request",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class ServiceUnavailableError(AppError):
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="SERVICE_UNAVAILABLE",
            details=details,
        )


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found"):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
        )


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict"):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
        )


INTERNAL_ERROR_BODY: dict[str, Any] = {
    "error": "INTERNAL_ERROR",
    "message": "An unexpected error occurred",
    "details": {},
}


def error_body(exc: AppError) -> dict[str, Any]:
    return {"error": exc.error_code, "message": exc.message, "details": exc.details}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    context = getattr(exc, "context", None)
    logger.warning(
        f"{exc.error_code}: {exc.message}",
        extra={
            "extra_data": {
                "error_code": exc.error_code,
                "details": exc.details,
                "path": str(request.url),
                **({"context": context} if context else {}),
            }
        },
    )
    return JSONResponse(
        status_code=exc.status_code, content=error_body(exc), headers=exc.headers
    )


def _jsonable_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Flatten pydantic errors, stringifying exception objects in ctx."""
    flat = []
    for err in exc.errors():
        ctx = err.get("ctx")
        if isinstance(ctx, dict):
            err = {**err, "ctx": {k: str(v) for k, v in ctx.items()}}
        flat.append(err)
    return flat


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = _jsonable_validation_errors(exc)
    logger.warning(
        "Validation error",
        extra={"extra_data": {"errors": errors, "path": str(request.url)}},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Invalid request data",
            "details": errors,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={"extra_data": {"path": str(request.url)}},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=INTERNAL_ERROR_BODY
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
