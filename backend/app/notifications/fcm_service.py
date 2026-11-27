"""Firebase Cloud Messaging (FCM) push dispatcher with safe unconfigured fallback."""

import importlib
import logging
from pathlib import Path

logger = logging.getLogger("jobmail.fcm")


class FCMDispatcher:
    """Sends push alerts via Firebase Admin SDK when credentials are configured."""

    def __init__(self, credentials_path: str = "") -> None:
        self._credentials_path = credentials_path.strip()
        self._app_initialized = False

    def _get_messaging_module(self):
        if not self._credentials_path:
            return None
        cred_file = Path(self._credentials_path)
        if not cred_file.exists():
            logger.warning("Firebase credentials file not found; skipping FCM push.")
            return None

        try:
            firebase_admin = importlib.import_module("firebase_admin")
            credentials = importlib.import_module("firebase_admin.credentials")
            messaging = importlib.import_module("firebase_admin.messaging")
        except ImportError:
            logger.info("firebase-admin package not installed; skipping FCM push.")
            return None

        if not self._app_initialized and not getattr(firebase_admin, "_apps", None):
            cred = credentials.Certificate(str(cred_file))
            firebase_admin.initialize_app(cred)
        self._app_initialized = True
        return messaging

    async def send_to_tokens(
        self,
        tokens: list[str],
        *,
        title: str,
        body: str,
        data: dict[str, str],
    ) -> int:
        """Dispatch push notifications to registered FCM tokens; returns sent count."""
        if not tokens:
            return 0
        messaging = self._get_messaging_module()
        if messaging is None:
            return 0

        sent = 0
        for token in tokens:
            try:
                msg = messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    data=data,
                    token=token,
                )
                messaging.send(msg)
                sent += 1
            except Exception as exc:
                logger.warning("Failed to deliver FCM notification: %s", type(exc).__name__)
        return sent
