"""Application logging configuration with PII/secret redaction and request tracing."""

import logging
import re
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"GOCSPX-[A-Za-z0-9_\-]+"), "[REDACTED_OAUTH_SECRET]"),
    (re.compile(r"ya29\.[A-Za-z0-9_\-]+"), "[REDACTED_ACCESS_TOKEN]"),
    (re.compile(r"1//[A-Za-z0-9_\-]+"), "[REDACTED_REFRESH_TOKEN]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"), "[REDACTED_JWT]"),
)


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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs HTTP method, path, status code, request ID, and latency without headers or bodies."""

    async def dispatch(self, request: Request, call_next) -> Response:
        logger = logging.getLogger("jobmail.http")
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        response.headers.setdefault("X-Request-ID", request_id)
        logger.info(
            "[%s] %s %s -> %d (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
