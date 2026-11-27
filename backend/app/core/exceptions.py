"""Domain exceptions and sanitized FastAPI error handlers."""

import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger("jobmail.exceptions")


class AppError(Exception):
    """Base application error mapped to structured HTTP responses."""

    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        detail: str,
        status_code: int | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        self.headers = headers or {}
        super().__init__(detail)


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED


class AccountLockedError(AuthenticationError):
    status_code = status.HTTP_423_LOCKED

    def __init__(self, detail: str, *, retry_after: int | None = None) -> None:
        headers = {"Retry-After": str(retry_after)} if retry_after else {}
        super().__init__(detail, status_code=self.status_code, headers=headers)


class AuthorizationError(AppError):
    status_code = status.HTTP_403_FORBIDDEN


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, detail: str, *, retry_after: int | None = None) -> None:
        headers = {"Retry-After": str(retry_after)} if retry_after else {}
        super().__init__(detail, status_code=self.status_code, headers=headers)


class ServiceNotConfiguredError(AppError):
    status_code = status.HTTP_501_NOT_IMPLEMENTED


class OAuthError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST


class OAuthRevokedError(AuthenticationError):
    pass


class ExternalServiceError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers returning sanitized JSON errors."""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers or None,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "[%s] Unhandled error on %s %s: %s",
            request_id,
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred."},
        )
