"""Google OAuth 2.0 HTTP client supporting PKCE (S256), token exchange, refresh, profile, and revocation."""

from dataclasses import dataclass
import logging
from urllib.parse import urlencode
import httpx
from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    OAuthError,
    OAuthRevokedError,
)

logger = logging.getLogger("jobmail.google_oauth")

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
GMAIL_PROFILE_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
REQUIRED_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@dataclass(frozen=True)
class GoogleTokenPayload:
    access_token: str
    expires_in: int
    refresh_token: str | None
    scope: str
    token_type: str


@dataclass(frozen=True)
class GmailProfilePayload:
    email_address: str
    history_id: str | None = None


class GoogleOAuthClient:
    """Async Google OAuth 2.0 and minimal profile client using read-only Gmail scope."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=15.0,
            transport=self._transport,
        )

    def build_authorization_url(
        self,
        state: str,
        *,
        code_challenge: str | None = None,
    ) -> str:
        """Construct Google OAuth 2.0 consent URL requesting offline read-only Gmail access + PKCE."""
        scopes = self._settings.google_oauth_scopes.strip() or REQUIRED_GMAIL_SCOPE
        params: dict[str, str] = {
            "client_id": self._settings.google_client_id.strip(),
            "redirect_uri": self._settings.google_redirect_uri.strip(),
            "response_type": "code",
            "scope": scopes,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        code: str,
        *,
        code_verifier: str | None = None,
    ) -> GoogleTokenPayload:
        """Exchange a one-time OAuth authorization code (with PKCE verifier) for tokens."""
        payload: dict[str, str] = {
            "code": code,
            "client_id": self._settings.google_client_id.strip(),
            "client_secret": self._settings.google_client_secret.strip(),
            "redirect_uri": self._settings.google_redirect_uri.strip(),
            "grant_type": "authorization_code",
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier
        data = await self._post_token_request(payload, context="code exchange")
        return self._parse_token_payload(data)

    async def refresh_access_token(self, refresh_token: str) -> GoogleTokenPayload:
        """Refresh an expired Gmail access token using a stored refresh token."""
        payload = {
            "client_id": self._settings.google_client_id.strip(),
            "client_secret": self._settings.google_client_secret.strip(),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        data = await self._post_token_request(payload, context="token refresh")
        return self._parse_token_payload(data)

    async def fetch_gmail_profile(self, access_token: str) -> GmailProfilePayload:
        """Fetch authenticated Gmail address and current historyId using gmail.readonly scope."""
        try:
            async with self._create_client() as client:
                response = await client.get(
                    GMAIL_PROFILE_ENDPOINT,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            logger.warning("Network error fetching Gmail profile: %s", type(exc).__name__)
            raise ExternalServiceError(
                "Unable to contact Google Gmail API while verifying account."
            ) from exc

        if response.status_code == 401:
            raise AuthenticationError("Google access token was rejected.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"Gmail profile request failed with status {response.status_code}."
            )

        body = response.json()
        email = str(body.get("emailAddress") or "").strip().lower()
        if not email:
            raise ExternalServiceError("Gmail profile response did not include an email address.")
        history_id = body.get("historyId")
        return GmailProfilePayload(
            email_address=email,
            history_id=str(history_id) if history_id is not None else None,
        )

    async def revoke_token(self, token: str) -> bool:
        """Best-effort revocation of an OAuth token with Google."""
        if not token:
            return False
        try:
            async with self._create_client() as client:
                response = await client.post(
                    GOOGLE_REVOKE_ENDPOINT,
                    params={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def _post_token_request(
        self, payload: dict[str, str], *, context: str
    ) -> dict:
        try:
            async with self._create_client() as client:
                response = await client.post(
                    GOOGLE_TOKEN_ENDPOINT,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            logger.warning("Network error during Google %s: %s", context, type(exc).__name__)
            raise ExternalServiceError(
                "Unable to reach Google OAuth servers. Please check your network connection."
            ) from exc

        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code >= 400:
            err_code = str(data.get("error") or "").strip()
            err_desc = str(data.get("error_description") or "").strip()
            if err_code == "invalid_grant":
                if context == "token refresh":
                    raise OAuthRevokedError(
                        "Gmail access was revoked or expired. Please reconnect this account."
                    )
                raise OAuthError(
                    err_desc or "Authorization code is invalid or expired. Please try connecting again."
                )
            if err_code == "redirect_uri_mismatch":
                raise OAuthError(
                    "Google OAuth redirect URI mismatch. Verify GOOGLE_REDIRECT_URI matches Google Cloud Console."
                )
            if err_code == "invalid_client":
                raise OAuthError(
                    "Invalid Google OAuth client configuration. Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
                )
            raise OAuthError(
                err_desc or f"Google OAuth {context} failed ({response.status_code})."
            )

        return data

    @staticmethod
    def _parse_token_payload(data: dict) -> GoogleTokenPayload:
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise ExternalServiceError("Google OAuth response missing access_token.")
        expires_in_raw = data.get("expires_in", 3600)
        try:
            expires_in = max(60, int(expires_in_raw))
        except (TypeError, ValueError):
            expires_in = 3600

        refresh_raw = data.get("refresh_token")
        refresh_token = str(refresh_raw).strip() if refresh_raw else None

        return GoogleTokenPayload(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
            scope=str(data.get("scope") or REQUIRED_GMAIL_SCOPE),
            token_type=str(data.get("token_type") or "Bearer"),
        )
