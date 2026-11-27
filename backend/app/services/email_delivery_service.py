"""Outbound transactional email dispatcher for verification and password reset."""

import asyncio
from email.message import EmailMessage
import logging
import smtplib
from app.core.config import Settings
from app.core.logging import mask_email

logger = logging.getLogger("jobmail.mailer")


class EmailDeliveryService:
    """Sends verification and reset emails via SMTP, or logs redacted notices in dev/test."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def smtp_configured(self) -> bool:
        return bool(
            self._settings.smtp_host.strip()
            and self._settings.smtp_from_email.strip()
        )

    async def send_verification_email(self, *, recipient: str, token: str) -> bool:
        verify_url = f"{self._settings.frontend_url.rstrip('/')}/verify-email?token={token}"
        subject = "Verify your JobMail email address"
        body = (
            "Welcome to JobMail.\n\n"
            "Please verify your email address using this verification code or link:\n"
            f"Verification Link: {verify_url}\n"
            f"Verification Token: {token}\n\n"
            "This token expires in 24 hours. If you did not create a JobMail account, ignore this email."
        )
        return await self._deliver(recipient=recipient, subject=subject, body=body, kind="verification")

    async def send_password_reset_email(self, *, recipient: str, token: str) -> bool:
        reset_url = f"{self._settings.frontend_url.rstrip('/')}/reset-password?token={token}"
        subject = "Reset your JobMail password"
        body = (
            "A password reset was requested for your JobMail account.\n\n"
            f"Reset Link: {reset_url}\n"
            f"Reset Token: {token}\n\n"
            "This token expires in 30 minutes and can be used once. "
            "If you did not request a reset, ignore this email."
        )
        return await self._deliver(recipient=recipient, subject=subject, body=body, kind="password_reset")

    async def _deliver(
        self, *, recipient: str, subject: str, body: str, kind: str
    ) -> bool:
        if not self.smtp_configured:
            logger.info(
                "SMTP not configured; %s email queued locally for %s (token suppressed from logs).",
                kind,
                mask_email(recipient),
            )
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._settings.smtp_from_email.strip()
        msg["To"] = recipient
        msg.set_content(body)

        await asyncio.to_thread(self._send_sync, msg)
        logger.info("Sent %s email via SMTP to %s.", kind, mask_email(recipient))
        return True

    def _send_sync(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(
            self._settings.smtp_host.strip(),
            self._settings.smtp_port,
            timeout=15,
        ) as server:
            if self._settings.smtp_use_tls:
                server.starttls()
            if self._settings.smtp_username.strip():
                server.login(
                    self._settings.smtp_username.strip(),
                    self._settings.smtp_password,
                )
            server.send_message(msg)
