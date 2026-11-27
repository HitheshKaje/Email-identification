"""Official Gmail REST API v1 client with pagination, strict nh3 sanitization, and rate-limit retries."""

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
from html.parser import HTMLParser
import logging
import re
from typing import Any, Awaitable, Callable
import httpx
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ExternalServiceError,
)

logger = logging.getLogger("jobmail.gmail_client")

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_WHITESPACE_RE = re.compile(r"\s+")
_CTRL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_STRIP_FALLBACK_RE = re.compile(r"<[^>]+>")


class HistoryExpiredError(Exception):
    """Raised when Gmail historyId is no longer available (HTTP 404)."""


@dataclass(frozen=True)
class GmailMessageListPage:
    message_ids: list[str]
    next_page_token: str | None = None


@dataclass(frozen=True)
class GmailHistoryPage:
    added_message_ids: list[str]
    next_page_token: str | None = None
    history_id: str | None = None


@dataclass(frozen=True)
class ParsedGmailMessage:
    gmail_message_id: str
    thread_id: str | None
    history_id: str | None
    sender: str
    subject: str
    snippet: str
    body_preview: str
    received_at: datetime
    has_attachments: bool = False
    attachment_names: list[str] = field(default_factory=list)


class GmailClient:
    """Async Gmail API v1 HTTP client with pagination, backoff retries, and safe parsing."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 3,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._transport = transport
        self._max_retries = max_retries
        self._sleep = sleep_fn

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=20.0, transport=self._transport)

    async def list_messages(
        self,
        access_token: str,
        *,
        page_token: str | None = None,
        max_results: int = 25,
        query: str | None = None,
    ) -> GmailMessageListPage:
        """Fetch a single paginated page of Gmail message IDs."""
        params: dict[str, Any] = {"maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        if query:
            params["q"] = query

        data = await self._get_json(
            f"{GMAIL_API_BASE}/messages",
            access_token=access_token,
            params=params,
        )
        raw_messages = data.get("messages") or []
        ids = [
            str(m["id"])
            for m in raw_messages
            if isinstance(m, dict) and m.get("id")
        ]
        return GmailMessageListPage(
            message_ids=ids,
            next_page_token=data.get("nextPageToken"),
        )

    async def list_history(
        self,
        access_token: str,
        *,
        start_history_id: str,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> GmailHistoryPage:
        """Fetch newly added message IDs since `start_history_id`."""
        params: dict[str, Any] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token

        data = await self._get_json(
            f"{GMAIL_API_BASE}/history",
            access_token=access_token,
            params=params,
            allow_history_404=True,
        )
        added_ids: list[str] = []
        seen: set[str] = set()
        for record in data.get("history") or []:
            for added in record.get("messagesAdded") or []:
                msg = added.get("message") or {}
                msg_id = str(msg.get("id") or "")
                if msg_id and msg_id not in seen:
                    seen.add(msg_id)
                    added_ids.append(msg_id)

        history_id = data.get("historyId")
        return GmailHistoryPage(
            added_message_ids=added_ids,
            next_page_token=data.get("nextPageToken"),
            history_id=str(history_id) if history_id is not None else None,
        )

    async def get_message(
        self, access_token: str, message_id: str
    ) -> ParsedGmailMessage:
        """Retrieve a single Gmail message and extract sanitized text and safe metadata."""
        data = await self._get_json(
            f"{GMAIL_API_BASE}/messages/{message_id}",
            access_token=access_token,
            params={"format": "full"},
        )
        return parse_gmail_message(data)

    async def _get_json(
        self,
        url: str,
        *,
        access_token: str,
        params: dict[str, Any] | None = None,
        allow_history_404: bool = False,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}"}

        for attempt in range(self._max_retries + 1):
            try:
                async with self._create_client() as client:
                    response = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    await self._sleep(0.5 * (2**attempt))
                    continue
                logger.warning("Gmail API network failure: %s", type(exc).__name__)
                raise ExternalServiceError(
                    "Unable to reach Gmail API due to a network error."
                ) from exc

            if response.status_code == 200:
                return response.json()

            if response.status_code == 401:
                raise AuthenticationError("Gmail OAuth access token expired or invalid.")

            if response.status_code == 404 and allow_history_404:
                raise HistoryExpiredError("Gmail historyId is expired or invalid.")

            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < self._max_retries:
                    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                    delay = retry_after if retry_after is not None else 0.5 * (2**attempt)
                    await self._sleep(min(delay, 8.0))
                    continue
                raise ExternalServiceError(
                    f"Gmail API temporarily unavailable or rate-limited ({response.status_code})."
                )

            if response.status_code == 403:
                reason = _extract_google_error_message(response)
                raise AuthorizationError(
                    reason or "Gmail API access forbidden or quota exceeded."
                )

            reason = _extract_google_error_message(response)
            raise ExternalServiceError(
                reason or f"Gmail API request failed with status {response.status_code}."
            )

        raise ExternalServiceError("Gmail API request exceeded maximum retries.")


def _parse_retry_after(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return max(0.1, float(raw.strip()))
    except ValueError:
        return None


def _extract_google_error_message(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "").strip() or None
    if isinstance(error, str):
        return error.strip() or None
    return None


_BLOCKED_HTML_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "svg",
    "noscript",
    "template",
}


class _StrictTextHTMLParser(HTMLParser):
    """State-machine HTML parser that extracts plain text only and drops dangerous subtrees."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _BLOCKED_HTML_TAGS:
            self._skip_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "hr"}:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in _BLOCKED_HTML_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif lower in {"p", "div", "li", "tr", "td", "h1", "h2", "h3", "h4"}:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(html.unescape(f"&#{name};"))

    def handle_comment(self, data: str) -> None:
        return None

    def get_text(self) -> str:
        return "".join(self._parts)


def sanitize_untrusted_text(raw: str) -> str:
    """Strictly remove HTML/script/style markup, comments, and control bytes from email content."""
    if not raw:
        return ""
    parser = _StrictTextHTMLParser()
    parser.feed(raw)
    parser.close()
    extracted = html.unescape(parser.get_text())
    without_leftover_tags = _TAG_STRIP_FALLBACK_RE.sub(" ", extracted)
    return _CTRL_CHARS_RE.sub("", without_leftover_tags)


def parse_gmail_message(raw: dict[str, Any]) -> ParsedGmailMessage:
    """Parse raw Gmail API message JSON into sanitized metadata + preview (no active HTML or binaries)."""
    payload = raw.get("payload") or {}
    headers_list = payload.get("headers") or []
    headers: dict[str, str] = {}
    for item in headers_list:
        if isinstance(item, dict) and item.get("name"):
            headers[str(item["name"]).lower()] = str(item.get("value") or "")

    sender = _normalize_preview(
        sanitize_untrusted_text(headers.get("from", "").strip()), max_chars=320
    ) or "Unknown Sender"
    subject = _normalize_preview(
        sanitize_untrusted_text(headers.get("subject", "").strip()), max_chars=400
    ) or "(No Subject)"
    received_at = _parse_timestamp(headers.get("date"), raw.get("internalDate"))

    raw_snippet = sanitize_untrusted_text(str(raw.get("snippet") or "")).strip()
    body_text, attachments = _extract_text_and_attachment_names(payload)
    preview_source = body_text or raw_snippet
    body_preview = _normalize_preview(preview_source, max_chars=1200)
    snippet = _normalize_preview(raw_snippet or body_preview, max_chars=280)

    history_raw = raw.get("historyId")
    return ParsedGmailMessage(
        gmail_message_id=str(raw.get("id") or ""),
        thread_id=str(raw["threadId"]) if raw.get("threadId") else None,
        history_id=str(history_raw) if history_raw is not None else None,
        sender=sender,
        subject=subject,
        snippet=snippet,
        body_preview=body_preview,
        received_at=received_at,
        has_attachments=bool(attachments),
        attachment_names=attachments[:10],
    )


def _parse_timestamp(date_header: str | None, internal_date_ms: Any) -> datetime:
    if date_header:
        try:
            dt = parsedate_to_datetime(date_header.strip())
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, IndexError):
            pass

    if internal_date_ms is not None:
        try:
            ms = int(internal_date_ms)
            return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError):
            pass

    return datetime.now(timezone.utc)


def _extract_text_and_attachment_names(
    payload: dict[str, Any],
) -> tuple[str, list[str]]:
    plain_chunks: list[str] = []
    html_chunks: list[str] = []
    attachment_names: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime_type = str(part.get("mimeType") or "").lower()
        filename = _normalize_preview(
            sanitize_untrusted_text(str(part.get("filename") or "")),
            max_chars=120,
        )
        body = part.get("body") or {}
        if filename or body.get("attachmentId"):
            attachment_names.append(filename or "unnamed-attachment")
            return

        data = body.get("data")
        if data and mime_type in ("text/plain", "text/html"):
            decoded = _decode_base64url(str(data))
            if decoded:
                if mime_type == "text/plain":
                    plain_chunks.append(sanitize_untrusted_text(decoded))
                else:
                    html_chunks.append(_strip_html(decoded))

        for child in part.get("parts") or []:
            if isinstance(child, dict):
                walk(child)

    walk(payload)
    if plain_chunks:
        return "\n".join(plain_chunks), attachment_names
    if html_chunks:
        return "\n".join(html_chunks), attachment_names
    return "", attachment_names


def _decode_base64url(data: str) -> str:
    try:
        padding = "=" * (-len(data) % 4)
        raw_bytes = base64.urlsafe_b64decode(data + padding)
        return raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(raw_html: str) -> str:
    return sanitize_untrusted_text(raw_html)


def _normalize_preview(text: str, *, max_chars: int) -> str:
    collapsed = _WHITESPACE_RE.sub(" ", text).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."
