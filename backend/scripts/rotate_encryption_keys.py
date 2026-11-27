"""Rotate MultiFernet-encrypted database fields using TOKEN_ENCRYPTION_KEYS="new-key,old-key"."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.authentication.encryption import TokenEncryptor, rotate_document_fields  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.database.mongodb import db_manager  # noqa: E402


async def run_rotation() -> None:
    settings = get_settings()
    if len(settings.encryption_key_list) < 2:
        print(
            "Provide TOKEN_ENCRYPTION_KEYS='<new_fernet_key>,<old_fernet_key>' before running rotation."
        )
        return

    encryptor = TokenEncryptor(settings.encryption_key_list)
    db = await db_manager.connect(settings)
    rotated_total = 0

    try:
        collections: list[tuple[str, tuple[str, ...]]] = [
            ("users", ("mfa_secret_enc", "mfa_pending_secret_enc")),
            ("connected_accounts", ("encrypted_access_token", "encrypted_refresh_token")),
            (
                "emails",
                (
                    "encrypted_sender",
                    "encrypted_subject",
                    "encrypted_body_preview",
                    "encrypted_company_name",
                    "encrypted_job_role",
                ),
            ),
            (
                "classification_feedback",
                ("encrypted_subject", "encrypted_body_preview", "encrypted_sender"),
            ),
            ("sync_history", ("encrypted_email_address",)),
        ]

        for collection_name, fields in collections:
            cursor = db[collection_name].find({})
            async for doc in cursor:
                updates = rotate_document_fields(encryptor, doc, fields)
                if updates:
                    await db[collection_name].update_one(
                        {"_id": doc["_id"]}, {"$set": updates}
                    )
                    rotated_total += 1
        print(f"Key rotation complete across {rotated_total} document(s).")
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(run_rotation())
