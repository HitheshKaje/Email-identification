"""JobMail FastAPI application factory with security headers, payload caps, CORS, and lifespan."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import auth, classification, dashboard, emails, notifications, privacy
from app.background.sync_scheduler import BackgroundSyncScheduler
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.database.mongodb import db_manager
from app.models.schemas import HealthResponse


class _PayloadTooLargeError(Exception):
    pass


class RequestSizeLimitMiddleware:
    """Reject oversized HTTP request payloads before full JSON decoding."""

    def __init__(self, app, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        raw_len = headers.get(b"content-length")
        if raw_len is not None:
            try:
                if int(raw_len) > self.max_bytes:
                    resp = JSONResponse(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        content={"detail": "Request payload exceeds allowed size limit."},
                    )
                    await resp(scope, receive, send)
                    return
            except ValueError:
                pass

        received_bytes = 0

        async def limited_receive():
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_bytes:
                    raise _PayloadTooLargeError()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLargeError:
            resp = JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": "Request payload exceeds allowed size limit."},
            )
            await resp(scope, receive, send)


class SecurityHeadersMiddleware:
    """Attach standard HTTP security headers and anti-caching controls on sensitive routes."""

    def __init__(self, app, *, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in raw_headers}

                def add_header(name: bytes, value: bytes) -> None:
                    if name.lower() not in existing:
                        raw_headers.append((name, value))
                        existing.add(name.lower())

                add_header(b"x-content-type-options", b"nosniff")
                add_header(b"x-frame-options", b"DENY")
                add_header(b"referrer-policy", b"strict-origin-when-cross-origin")
                add_header(
                    b"permissions-policy",
                    b"geolocation=(), microphone=(), camera=()",
                )
                if path.startswith("/auth/google/callback"):
                    add_header(
                        b"content-security-policy",
                        b"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
                    )
                else:
                    add_header(
                        b"content-security-policy",
                        b"default-src 'none'; frame-ancestors 'none'",
                    )

                if path.startswith(("/auth", "/privacy", "/emails")):
                    add_header(b"cache-control", b"no-store")
                    add_header(b"pragma", b"no-cache")

                if self.settings.is_production or scope.get("scheme") == "https":
                    add_header(
                        b"strict-transport-security",
                        b"max-age=31536000; includeSubDomains",
                    )

                message["headers"] = raw_headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    db = await db_manager.connect(settings)
    scheduler: BackgroundSyncScheduler | None = None
    if settings.auto_sync_enabled and settings.environment != "test":
        scheduler = BackgroundSyncScheduler(db, settings)
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()
        await db_manager.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    resolved_settings = settings or get_settings()

    docs_url = "/docs" if resolved_settings.docs_enabled else None
    redoc_url = "/redoc" if resolved_settings.docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.docs_enabled else None

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.3.0",
        description="Intelligent Job Email Assistant REST API",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    if resolved_settings.trusted_host_list:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=resolved_settings.trusted_host_list,
        )

    allow_origin_regex = (
        r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        if not resolved_settings.is_production
        else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-CSRF-Token",
            "X-Request-ID",
        ],
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=resolved_settings)
    app.add_middleware(
        RequestSizeLimitMiddleware, max_bytes=resolved_settings.max_request_body_bytes
    )
    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def health_check() -> JSONResponse:
        db_ok = await db_manager.ping()
        payload = HealthResponse(
            status="ok" if db_ok else "degraded",
            database="connected" if db_ok else "disconnected",
            environment=resolved_settings.environment,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK
            if db_ok
            else status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )

    app.include_router(auth.router)
    app.include_router(privacy.router)
    app.include_router(dashboard.router)
    app.include_router(emails.router)
    app.include_router(notifications.router)
    app.include_router(classification.router)

    return app


app = create_app()
