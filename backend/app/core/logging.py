"""Application logging configuration with PII/secret redaction and request tracing."""

import logging
import re
import time
import uuid
from urllib.parse import urlparse

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE), r"\1[REDACTED]"),
    (
        re.compile(r"(mongodb(?:\+srv)?://[^:\s/@]+:)([^@\s]+)(@)", re.IGNORECASE),
        r"\1[REDACTED]\3",
    ),
    (re.compile(r"GOCSPX-[A-Za-z0-9_\-]+"), "[REDACTED_OAUTH_SECRET]"),
    (re.compile(r"ya29\.[A-Za-z0-9_\-]+"), "[REDACTED_ACCESS_TOKEN]"),
    (re.compile(r"1//[A-Za-z0-9_\-]+"), "[REDACTED_REFRESH_TOKEN]"),
    (re.compile(r"([?&](?:code|state)=)[^&\s\"']+"), r"\1[REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"), "[REDACTED_JWT]"),
)


def sanitize_mongodb_uri(uri: str | None) -> str:
    """Return a credential-free description of a MongoDB connection URI for safe logging."""
    raw = (uri or "").strip()
    if not raw:
        return "[unset]"
    parsed = urlparse(raw)
    if parsed.scheme and parsed.hostname:
        port_part = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port_part}"
    return redact_sensitive_text(raw)


def mask_email(email: str | None) -> str:
    """Return privacy-preserving masked email identifier for logs (e.g., h***@gmail.com)."""
    if not email or "@" not in email:
        return "[redacted]"
    local, domain = email.split("@", 1)
    prefix = local[0] if local else "*"
    return f"{prefix}***@{domain}"


def redact_sensitive_text(text: str) -> str:
    cleaned = text
    for pattern, repl in _SECRET_PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    return cleaned


class SensitiveDataFilter(logging.Filter):
    """Log filter scrubbing bearer tokens, OAuth secrets, and JWTs from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            scrubbed = redact_sensitive_text(rendered)
            if scrubbed != rendered:
                record.msg = scrubbed
                record.args = ()
        except Exception:
            pass
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    jobmail_logger = logging.getLogger("jobmail")
    if not any(isinstance(f, SensitiveDataFilter) for f in jobmail_logger.filters):
        jobmail_logger.addFilter(SensitiveDataFilter())


class RequestLoggingMiddleware:
    """Pure ASGI middleware logging HTTP method, path, status, request ID, and latency."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        logger = logging.getLogger("jobmail.http")
        raw_headers = scope.get("headers", [])
        request_id = ""
        for k, v in raw_headers:
            if k.lower() == b"x-request-id":
                request_id = v.decode("latin-1").strip()[:64]
                break
        if not request_id:
            request_id = uuid.uuid4().hex[:12]

        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        start = time.perf_counter()
        status_code = 500
        req_id_bytes = request_id.encode("latin-1")

        async def send_with_request_id(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in headers):
                    headers.append((b"x-request-id", req_id_bytes))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.info(
                "[%s] %s %s -> %d (%.1fms)",
                request_id,
                scope.get("method", "?"),
                scope.get("path", "?"),
                status_code,
                elapsed_ms,
            )
