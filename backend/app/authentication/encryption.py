"""Symmetric encryption and key-rotation helpers for OAuth tokens and sensitive DB fields."""

import hashlib
import hmac
from typing import Iterable
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from app.core.exceptions import AppError


class TokenEncryptor:
    """Encrypts, decrypts, and rotates sensitive values using MultiFernet."""

    def __init__(self, key_or_keys: str | Iterable[str]) -> None:
        if isinstance(key_or_keys, str):
            raw_keys = [k.strip() for k in key_or_keys.split(",") if k.strip()]
        else:
            raw_keys = [str(k).strip() for k in key_or_keys if str(k).strip()]

        if not raw_keys:
            raise AppError("No encryption key configured.")

        self._keys = raw_keys
        self._fernets = [Fernet(k.encode("ascii")) for k in raw_keys]
        self._multi = MultiFernet(self._fernets)

    @property
    def primary_key(self) -> str:
        return self._keys[0]

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise AppError("Cannot encrypt an empty value.")
        return self._multi.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._multi.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise AppError("Stored credential could not be decrypted.") from exc

    def rotate(self, ciphertext: str) -> str:
        """Re-encrypt ciphertext produced by an older key under the active primary key."""
        try:
            return self._multi.rotate(ciphertext.encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError) as exc:
            raise AppError("Stored credential could not be rotated.") from exc

    def encrypt_optional(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return self.encrypt(cleaned)

    def decrypt_optional(self, ciphertext: str | None) -> str | None:
        if not ciphertext:
            return None
        return self.decrypt(ciphertext)

    def blind_index(self, value: str, purpose: str = "lookup") -> str:
        """Return deterministic keyed HMAC-SHA256 digest for privacy-safe matching."""
        key = self.primary_key.encode("ascii")
        msg = f"{purpose}:{value.strip().lower()}".encode("utf-8")
        return hmac.new(key, msg, hashlib.sha256).hexdigest()


def rotate_document_fields(
    encryptor: TokenEncryptor,
    doc: dict,
    fields: tuple[str, ...],
) -> dict[str, str]:
    """Return updated ciphertext dict for non-empty encrypted fields in a MongoDB document."""
    updates: dict[str, str] = {}
    for field in fields:
        raw = doc.get(field)
        if isinstance(raw, str) and raw.strip():
            updates[field] = encryptor.rotate(raw.strip())
    return updates
