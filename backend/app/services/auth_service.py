"""Hardened authentication lifecycle, Argon2id upgrades, MFA, lockouts, and rotating sessions."""

from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from app.authentication.encryption import TokenEncryptor
from app.authentication.security import (
    build_totp_uri,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    generate_recovery_codes,
    generate_totp_secret,
    hash_opaque_token,
    hash_password,
    needs_password_rehash,
    validate_password_strength,
    verify_opaque_token_hash,
    verify_password,
    verify_totp_code,
)
from app.core.config import Settings
from app.core.exceptions import (
    AccountLockedError,
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
)
from app.core.logging import mask_email
from app.models.enums import AccountSyncStatus, UserRole
from app.models.schemas import (
    ConnectedAccountResponse,
    LoginRequest,
    MfaSetupResponse,
    NotificationPreferencesSchema,
    RegisterRequest,
    SessionInfoResponse,
    TokenResponse,
    UserResponse,
)
from app.services.db_utils import parse_object_id
from app.services.email_delivery_service import EmailDeliveryService
from app.services.security_audit_service import SecurityAuditService


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _user_doc_to_response(doc: dict) -> UserResponse:
    return UserResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        email=doc["email"],
        created_at=doc["created_at"],
        email_verified=bool(doc.get("email_verified", False)),
        mfa_enabled=bool(doc.get("mfa_enabled", False)),
        role=str(doc.get("role", UserRole.USER.value)),
        last_login_at=doc.get("last_login_at"),
        last_login_ip=doc.get("last_login_ip"),
        data_retention_days=int(doc.get("data_retention_days", 180)),
    )


class AuthService:
    """Manages Argon2id credentials, verification, resets, TOTP MFA, and server-side sessions."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        *,
        mailer: EmailDeliveryService | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._encryptor = TokenEncryptor(settings.encryption_key_list)
        self._audit = SecurityAuditService(db)
        self._mailer = mailer or EmailDeliveryService(settings)

    async def register_user(
        self,
        payload: RegisterRequest,
        *,
        ip_address: str | None = None,
        device_info: str = "JobMail Client",
    ) -> TokenResponse:
        validate_password_strength(payload.password)
        normalized_email = payload.email.strip().lower()
        now = datetime.now(timezone.utc)
        doc = {
            "name": payload.name.strip(),
            "email": normalized_email,
            "hashed_password": hash_password(payload.password),
            "password_algo": "argon2id",
            "role": UserRole.USER.value,
            "email_verified": False,
            "mfa_enabled": False,
            "mfa_secret_enc": "",
            "mfa_recovery_hashes": [],
            "failed_login_attempts": 0,
            "locked_until": None,
            "last_login_at": now,
            "last_login_ip": ip_address,
            "data_retention_days": self._settings.default_data_retention_days,
            "notification_preferences": NotificationPreferencesSchema().model_dump(),
            "created_at": now,
            "password_changed_at": now,
        }
        try:
            result = await self._db.users.insert_one(doc)
        except DuplicateKeyError as exc:
            raise ConflictError("An account with this email already exists.") from exc

        doc["_id"] = result.inserted_id
        user = _user_doc_to_response(doc)

        await self._issue_verification_token(user_id=user.id, email=normalized_email)
        await self._audit.log_event(
            event_type="USER_REGISTERED",
            user_id=user.id,
            ip_address=ip_address,
            summary=f"Registered account {mask_email(normalized_email)}.",
        )
        return await self._create_session_tokens(
            user=user,
            ip_address=ip_address,
            device_info=device_info,
        )

    async def authenticate_user(
        self,
        payload: LoginRequest,
        *,
        ip_address: str | None = None,
        device_info: str = "JobMail Client",
    ) -> TokenResponse:
        normalized_email = payload.email.strip().lower()
        doc = await self._db.users.find_one({"email": normalized_email})
        now = datetime.now(timezone.utc)

        if not doc:
            await self._audit.log_event(
                event_type="LOGIN_FAILED",
                severity="medium",
                ip_address=ip_address,
                summary=f"Failed login attempt for unknown account {mask_email(normalized_email)}.",
            )
            raise AuthenticationError("Invalid email or password.")

        user_id = str(doc["_id"])
        locked_until = doc.get("locked_until")
        if isinstance(locked_until, datetime) and _as_utc(locked_until) > now:
            retry_after = max(1, int((_as_utc(locked_until) - now).total_seconds()))
            await self._audit.log_event(
                event_type="LOGIN_BLOCKED_LOCKED",
                severity="high",
                user_id=user_id,
                ip_address=ip_address,
                alert=True,
                summary="Blocked login attempt against locked account.",
            )
            raise AccountLockedError(
                "Account temporarily locked due to repeated failed login attempts. Try again later.",
                retry_after=retry_after,
            )

        if not verify_password(payload.password, doc["hashed_password"]):
            attempts = int(doc.get("failed_login_attempts", 0)) + 1
            updates: dict[str, object] = {"failed_login_attempts": attempts}
            is_lockout = attempts >= self._settings.max_failed_login_attempts
            if is_lockout:
                lock_until = now + timedelta(
                    minutes=self._settings.account_lockout_minutes
                )
                updates["locked_until"] = lock_until
            await self._db.users.update_one({"_id": doc["_id"]}, {"$set": updates})
            await self._audit.log_event(
                event_type="ACCOUNT_LOCKED" if is_lockout else "LOGIN_FAILED",
                severity="high" if is_lockout else "medium",
                user_id=user_id,
                ip_address=ip_address,
                alert=is_lockout or attempts >= 3,
                summary=f"Failed login attempt #{attempts} for {mask_email(normalized_email)}.",
            )
            if is_lockout:
                raise AccountLockedError(
                    "Account locked due to too many failed login attempts. Please wait or reset your password.",
                    retry_after=self._settings.account_lockout_minutes * 60,
                )
            raise AuthenticationError("Invalid email or password.")

        login_updates: dict[str, object] = {
            "failed_login_attempts": 0,
            "locked_until": None,
        }
        if needs_password_rehash(doc["hashed_password"]):
            login_updates["hashed_password"] = hash_password(payload.password)
            login_updates["password_algo"] = "argon2id"

        prev_ip = doc.get("last_login_ip")
        if prev_ip and ip_address and prev_ip != ip_address:
            await self._audit.log_event(
                event_type="NEW_DEVICE_LOGIN",
                severity="medium",
                user_id=user_id,
                ip_address=ip_address,
                alert=True,
                summary="Sign-in detected from a new IP address.",
            )

        if doc.get("mfa_enabled"):
            await self._db.users.update_one({"_id": doc["_id"]}, {"$set": login_updates})
            challenge = create_access_token(
                subject=user_id,
                settings=self._settings,
                role=str(doc.get("role", UserRole.USER.value)),
                expires_delta=timedelta(minutes=5),
                token_type="mfa_challenge",
            )
            return TokenResponse(
                access_token="",
                expires_in=300,
                mfa_required=True,
                mfa_challenge_token=challenge,
                user=_user_doc_to_response(doc),
            )

        login_updates["last_login_at"] = now
        login_updates["last_login_ip"] = ip_address
        updated_doc = await self._db.users.find_one_and_update(
            {"_id": doc["_id"]},
            {"$set": login_updates},
            return_document=True,
        )
        user = _user_doc_to_response(updated_doc or doc)
        await self._audit.log_event(
            event_type="LOGIN_SUCCESS",
            user_id=user.id,
            ip_address=ip_address,
            summary=f"Successful login for {mask_email(user.email)}.",
        )
        return await self._create_session_tokens(
            user=user,
            ip_address=ip_address,
            device_info=device_info,
        )

    async def verify_mfa_login(
        self,
        *,
        challenge_token: str,
        code: str,
        ip_address: str | None = None,
        device_info: str = "JobMail Client",
    ) -> TokenResponse:
        payload = decode_access_token(
            challenge_token,
            self._settings,
            expected_type="mfa_challenge",
        )
        user_id = str(payload["sub"])
        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one({"_id": oid})
        if not doc or not doc.get("mfa_enabled"):
            raise AuthenticationError("MFA verification failed.")

        if not await self._consume_mfa_or_recovery_code(doc, code):
            await self._audit.log_event(
                event_type="MFA_FAILED",
                severity="high",
                user_id=user_id,
                ip_address=ip_address,
                alert=True,
                summary="Invalid MFA verification code entered during sign-in.",
            )
            raise AuthenticationError("Invalid multi-factor authentication code.")

        now = datetime.now(timezone.utc)
        updated = await self._db.users.find_one_and_update(
            {"_id": oid},
            {"$set": {"last_login_at": now, "last_login_ip": ip_address}},
            return_document=True,
        )
        user = _user_doc_to_response(updated or doc)
        await self._audit.log_event(
            event_type="LOGIN_SUCCESS",
            user_id=user.id,
            ip_address=ip_address,
            summary="Successful MFA-verified login.",
        )
        return await self._create_session_tokens(
            user=user,
            ip_address=ip_address,
            device_info=device_info,
        )

    async def refresh_session(
        self,
        raw_refresh_token: str,
        *,
        ip_address: str | None = None,
    ) -> TokenResponse:
        if "." not in raw_refresh_token:
            raise AuthenticationError("Invalid refresh token format.")
        session_id, _ = raw_refresh_token.split(".", 1)
        now = datetime.now(timezone.utc)

        session_doc = await self._db.sessions.find_one({"session_id": session_id})
        if (
            not session_doc
            or session_doc.get("revoked_at") is not None
            or _as_utc(session_doc["expires_at"]) <= now
        ):
            raise AuthenticationError("Session has expired or been revoked.")

        presented_hash = hash_opaque_token(raw_refresh_token)
        stored_hash = str(session_doc.get("refresh_token_hash") or "")
        used_hashes = [str(h) for h in session_doc.get("used_refresh_hashes") or []]

        if not verify_opaque_token_hash(raw_refresh_token, stored_hash):
            if presented_hash in used_hashes:
                # Refresh-token reuse detected: compromise indicator -> revoke entire session!
                await self._db.sessions.update_one(
                    {"session_id": session_id},
                    {"$set": {"revoked_at": now}},
                )
                await self._audit.log_event(
                    event_type="SUSPICIOUS_TOKEN_REUSE",
                    severity="critical",
                    user_id=str(session_doc["user_id"]),
                    ip_address=ip_address,
                    alert=True,
                    summary=f"Refresh token reuse detected on session {session_id}; session revoked.",
                )
                raise AuthenticationError(
                    "Refresh token reuse detected. Session revoked for your security."
                )
            raise AuthenticationError("Invalid refresh token.")

        user = await self.get_user_by_id(str(session_doc["user_id"]))
        new_refresh = f"{session_id}.{generate_opaque_token(32)}"
        new_hash = hash_opaque_token(new_refresh)
        next_used = (used_hashes + [stored_hash])[-20:]
        new_expiry = now + timedelta(days=self._settings.refresh_token_expire_days)

        await self._db.sessions.update_one(
            {"session_id": session_id, "revoked_at": None},
            {
                "$set": {
                    "refresh_token_hash": new_hash,
                    "used_refresh_hashes": next_used,
                    "last_active_at": now,
                    "expires_at": new_expiry,
                    "ip_address": ip_address or session_doc.get("ip_address"),
                }
            },
        )
        access_token = create_access_token(
            subject=user.id,
            settings=self._settings,
            session_id=session_id,
            role=user.role,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            session_id=session_id,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
            user=user,
        )

    async def validate_active_session(self, user_id: str, session_id: str | None) -> None:
        if not session_id:
            raise AuthenticationError("Session identifier missing. Please sign in again.")
        now = datetime.now(timezone.utc)
        session = await self._db.sessions.find_one(
            {
                "session_id": session_id,
                "user_id": user_id,
                "revoked_at": None,
                "expires_at": {"$gt": now},
            }
        )
        if not session:
            raise AuthenticationError("Session expired or revoked. Please sign in again.")
        await self._db.sessions.update_one(
            {"_id": session["_id"]},
            {"$set": {"last_active_at": now}},
        )

    async def list_sessions(
        self, user_id: str, *, current_session_id: str | None = None
    ) -> list[SessionInfoResponse]:
        now = datetime.now(timezone.utc)
        cursor = self._db.sessions.find(
            {
                "user_id": user_id,
                "revoked_at": None,
                "expires_at": {"$gt": now},
            }
        ).sort("last_active_at", -1)
        docs = await cursor.to_list(length=50)
        return [
            SessionInfoResponse(
                id=str(doc["session_id"]),
                device_info=str(doc.get("device_info", "Unknown Device")),
                ip_address=doc.get("ip_address"),
                created_at=doc["created_at"],
                last_active_at=doc["last_active_at"],
                expires_at=doc["expires_at"],
                is_current=str(doc["session_id"]) == current_session_id,
            )
            for doc in docs
        ]

    async def revoke_session(
        self,
        user_id: str,
        session_id: str,
        *,
        ip_address: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        res = await self._db.sessions.update_one(
            {"session_id": session_id, "user_id": user_id, "revoked_at": None},
            {"$set": {"revoked_at": now}},
        )
        if res.matched_count == 0:
            raise NotFoundError("Session not found.")
        await self._audit.log_event(
            event_type="SESSION_REVOKED",
            user_id=user_id,
            ip_address=ip_address,
            summary=f"Revoked session {session_id[:12]}.",
        )

    async def logout_all_sessions(
        self,
        user_id: str,
        *,
        ip_address: str | None = None,
        except_session_id: str | None = None,
    ) -> int:
        now = datetime.now(timezone.utc)
        query: dict[str, object] = {"user_id": user_id, "revoked_at": None}
        if except_session_id:
            query["session_id"] = {"$ne": except_session_id}
        res = await self._db.sessions.update_many(query, {"$set": {"revoked_at": now}})
        if not except_session_id:
            await self._audit.log_event(
                event_type="LOGOUT_ALL_DEVICES",
                user_id=user_id,
                ip_address=ip_address,
                summary=f"Logged out from {res.modified_count} active session(s).",
            )
        return int(res.modified_count)

    async def request_email_verification(
        self, user_id: str, *, ip_address: str | None = None
    ) -> None:
        user = await self.get_user_by_id(user_id)
        if user.email_verified:
            return
        await self._issue_verification_token(user_id=user.id, email=user.email)
        await self._audit.log_event(
            event_type="EMAIL_VERIFICATION_REQUESTED",
            user_id=user.id,
            ip_address=ip_address,
            summary=f"Requested email verification for {mask_email(user.email)}.",
        )

    async def confirm_email_verification(
        self, raw_token: str, *, ip_address: str | None = None
    ) -> UserResponse:
        now = datetime.now(timezone.utc)
        token_doc = await self._db.verification_tokens.find_one_and_delete(
            {
                "token_hash": hash_opaque_token(raw_token.strip()),
                "purpose": "email_verify",
            }
        )
        if not token_doc or _as_utc(token_doc["expires_at"]) <= now:
            raise AppError("Verification token is invalid or expired.", status_code=400)

        oid = parse_object_id(str(token_doc["user_id"]), "User")
        updated = await self._db.users.find_one_and_update(
            {"_id": oid},
            {"$set": {"email_verified": True}},
            return_document=True,
        )
        if not updated:
            raise NotFoundError("User not found.")

        await self._audit.log_event(
            event_type="EMAIL_VERIFIED",
            user_id=str(oid),
            ip_address=ip_address,
            summary="Email address verified.",
        )
        return _user_doc_to_response(updated)

    async def request_password_reset(
        self, email: str, *, ip_address: str | None = None
    ) -> None:
        normalized_email = email.strip().lower()
        doc = await self._db.users.find_one({"email": normalized_email})
        if not doc:
            return

        user_id = str(doc["_id"])
        raw_token = generate_opaque_token(32)
        now = datetime.now(timezone.utc)
        await self._db.verification_tokens.delete_many(
            {"user_id": user_id, "purpose": "password_reset"}
        )
        await self._db.verification_tokens.insert_one(
            {
                "user_id": user_id,
                "purpose": "password_reset",
                "token_hash": hash_opaque_token(raw_token),
                "created_at": now,
                "expires_at": now + timedelta(minutes=30),
            }
        )
        await self._mailer.send_password_reset_email(
            recipient=normalized_email,
            token=raw_token,
        )
        await self._audit.log_event(
            event_type="PASSWORD_RESET_REQUESTED",
            user_id=user_id,
            ip_address=ip_address,
            summary=f"Password reset requested for {mask_email(normalized_email)}.",
        )

    async def confirm_password_reset(
        self,
        *,
        token: str,
        new_password: str,
        ip_address: str | None = None,
    ) -> None:
        validate_password_strength(new_password)
        now = datetime.now(timezone.utc)
        token_doc = await self._db.verification_tokens.find_one_and_delete(
            {
                "token_hash": hash_opaque_token(token.strip()),
                "purpose": "password_reset",
            }
        )
        if not token_doc or _as_utc(token_doc["expires_at"]) <= now:
            raise AppError("Password reset token is invalid or expired.", status_code=400)

        user_id = str(token_doc["user_id"])
        oid = parse_object_id(user_id, "User")
        res = await self._db.users.update_one(
            {"_id": oid},
            {
                "$set": {
                    "hashed_password": hash_password(new_password),
                    "password_algo": "argon2id",
                    "failed_login_attempts": 0,
                    "locked_until": None,
                    "password_changed_at": now,
                }
            },
        )
        if res.matched_count == 0:
            raise NotFoundError("User not found.")

        await self.logout_all_sessions(user_id, ip_address=ip_address)
        await self._audit.log_event(
            event_type="PASSWORD_RESET_COMPLETED",
            user_id=user_id,
            ip_address=ip_address,
            summary="Password reset completed and active sessions revoked.",
        )

    async def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
        current_session_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one({"_id": oid})
        if not doc or not verify_password(current_password, doc["hashed_password"]):
            await self._audit.log_event(
                event_type="PASSWORD_CHANGE_FAILED",
                severity="medium",
                user_id=user_id,
                ip_address=ip_address,
                summary="Incorrect current password supplied during password change.",
            )
            raise AuthenticationError("Current password is incorrect.")

        if current_password == new_password:
            raise AppError("New password must differ from the current password.", status_code=422)
        validate_password_strength(new_password)

        now = datetime.now(timezone.utc)
        await self._db.users.update_one(
            {"_id": oid},
            {
                "$set": {
                    "hashed_password": hash_password(new_password),
                    "password_algo": "argon2id",
                    "password_changed_at": now,
                }
            },
        )
        await self.logout_all_sessions(
            user_id,
            ip_address=ip_address,
            except_session_id=current_session_id,
        )
        await self._audit.log_event(
            event_type="PASSWORD_CHANGED",
            user_id=user_id,
            ip_address=ip_address,
            summary="Account password changed and other sessions revoked.",
        )

    async def setup_mfa(self, user_id: str) -> MfaSetupResponse:
        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one({"_id": oid})
        if not doc:
            raise NotFoundError("User not found.")

        secret = generate_totp_secret()
        plain_recovery, hashed_recovery = generate_recovery_codes(8)
        await self._db.users.update_one(
            {"_id": oid},
            {
                "$set": {
                    "mfa_pending_secret_enc": self._encryptor.encrypt(secret),
                    "mfa_pending_recovery_hashes": hashed_recovery,
                }
            },
        )
        uri = build_totp_uri(secret, doc["email"], issuer=self._settings.mfa_issuer)
        return MfaSetupResponse(
            secret=secret,
            provisioning_uri=uri,
            recovery_codes=plain_recovery,
        )

    async def enable_mfa(
        self, user_id: str, code: str, *, ip_address: str | None = None
    ) -> UserResponse:
        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one({"_id": oid})
        if not doc or not doc.get("mfa_pending_secret_enc"):
            raise AppError("Start MFA setup before confirming.", status_code=400)

        secret = self._encryptor.decrypt(str(doc["mfa_pending_secret_enc"]))
        if not verify_totp_code(secret, code):
            raise AuthenticationError("Invalid authenticator verification code.")

        updated = await self._db.users.find_one_and_update(
            {"_id": oid},
            {
                "$set": {
                    "mfa_enabled": True,
                    "mfa_secret_enc": doc["mfa_pending_secret_enc"],
                    "mfa_recovery_hashes": doc.get("mfa_pending_recovery_hashes", []),
                },
                "$unset": {
                    "mfa_pending_secret_enc": "",
                    "mfa_pending_recovery_hashes": "",
                },
            },
            return_document=True,
        )
        await self._audit.log_event(
            event_type="MFA_ENABLED",
            user_id=user_id,
            ip_address=ip_address,
            summary="Multi-factor authentication enabled.",
        )
        return _user_doc_to_response(updated or doc)

    async def disable_mfa(
        self,
        *,
        user_id: str,
        password: str,
        code: str,
        ip_address: str | None = None,
    ) -> UserResponse:
        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one({"_id": oid})
        if not doc or not verify_password(password, doc["hashed_password"]):
            raise AuthenticationError("Invalid password.")
        if not doc.get("mfa_enabled"):
            return _user_doc_to_response(doc)

        if not await self._consume_mfa_or_recovery_code(doc, code):
            raise AuthenticationError("Invalid MFA verification code.")

        updated = await self._db.users.find_one_and_update(
            {"_id": oid},
            {
                "$set": {
                    "mfa_enabled": False,
                    "mfa_secret_enc": "",
                    "mfa_recovery_hashes": [],
                }
            },
            return_document=True,
        )
        await self._audit.log_event(
            event_type="MFA_DISABLED",
            severity="medium",
            user_id=user_id,
            ip_address=ip_address,
            alert=True,
            summary="Multi-factor authentication disabled.",
        )
        return _user_doc_to_response(updated or doc)

    async def get_user_by_id(self, user_id: str) -> UserResponse:
        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one({"_id": oid})
        if not doc:
            raise AuthenticationError("User account not found.")
        return _user_doc_to_response(doc)

    async def update_user_name(self, user_id: str, name: str) -> UserResponse:
        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one_and_update(
            {"_id": oid},
            {"$set": {"name": name.strip()}},
            return_document=True,
        )
        if not doc:
            raise NotFoundError("User not found.")
        return _user_doc_to_response(doc)

    async def list_connected_accounts(
        self, user_id: str
    ) -> list[ConnectedAccountResponse]:
        cursor = self._db.connected_accounts.find(
            {"user_id": user_id},
            projection={
                "encrypted_refresh_token": 0,
                "encrypted_access_token": 0,
            },
        ).sort("connected_at", -1)
        docs = await cursor.to_list(length=50)
        return [account_doc_to_response(doc) for doc in docs]

    async def _create_session_tokens(
        self,
        *,
        user: UserResponse,
        ip_address: str | None,
        device_info: str,
    ) -> TokenResponse:
        now = datetime.now(timezone.utc)
        session_id = generate_opaque_token(18)
        refresh_token = f"{session_id}.{generate_opaque_token(32)}"
        expires_at = now + timedelta(days=self._settings.refresh_token_expire_days)

        await self._db.sessions.insert_one(
            {
                "session_id": session_id,
                "user_id": user.id,
                "refresh_token_hash": hash_opaque_token(refresh_token),
                "used_refresh_hashes": [],
                "device_info": device_info[:120],
                "ip_address": ip_address,
                "created_at": now,
                "last_active_at": now,
                "expires_at": expires_at,
                "revoked_at": None,
            }
        )
        access_token = create_access_token(
            subject=user.id,
            settings=self._settings,
            session_id=session_id,
            role=user.role,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            session_id=session_id,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
            user=user,
        )

    async def _issue_verification_token(self, *, user_id: str, email: str) -> None:
        raw_token = generate_opaque_token(32)
        now = datetime.now(timezone.utc)
        await self._db.verification_tokens.delete_many(
            {"user_id": user_id, "purpose": "email_verify"}
        )
        await self._db.verification_tokens.insert_one(
            {
                "user_id": user_id,
                "purpose": "email_verify",
                "token_hash": hash_opaque_token(raw_token),
                "created_at": now,
                "expires_at": now + timedelta(hours=24),
            }
        )
        await self._mailer.send_verification_email(recipient=email, token=raw_token)

    async def _consume_mfa_or_recovery_code(self, doc: dict, code: str) -> bool:
        enc_secret = str(doc.get("mfa_secret_enc") or "")
        if enc_secret:
            secret = self._encryptor.decrypt(enc_secret)
            if verify_totp_code(secret, code):
                return True

        cleaned_code = code.strip().upper()
        recovery_hashes = [str(h) for h in doc.get("mfa_recovery_hashes") or []]
        for stored_hash in recovery_hashes:
            if verify_opaque_token_hash(cleaned_code, stored_hash):
                remaining = [h for h in recovery_hashes if h != stored_hash]
                await self._db.users.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"mfa_recovery_hashes": remaining}},
                )
                return True
        return False


def account_doc_to_response(doc: dict) -> ConnectedAccountResponse:
    # Intentionally omit encrypted_access_token and encrypted_refresh_token from API serialization.
    return ConnectedAccountResponse(
        id=str(doc["_id"]),
        email_address=doc["email_address"],
        provider=doc.get("provider", "google"),
        connected_at=doc["connected_at"],
        last_synced_at=doc.get("last_synced_at"),
        sync_status=AccountSyncStatus(
            doc.get("sync_status", AccountSyncStatus.PENDING.value)
        ),
        status_message=doc.get("status_message"),
    )
