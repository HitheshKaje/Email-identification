"""Pydantic v2 request and response schemas for JobMail REST APIs."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from app.models.enums import AccountSyncStatus, EmailCategory


class HealthResponse(BaseModel):
    status: str
    database: str
    environment: str


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    created_at: datetime
    email_verified: bool = False
    mfa_enabled: bool = False
    role: str = "user"
    last_login_at: datetime | None = None
    last_login_ip: str | None = None
    data_retention_days: int = 180


class TokenResponse(BaseModel):
    access_token: str = ""
    refresh_token: str | None = None
    session_id: str | None = None
    expires_in: int = 900
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_challenge_token: str | None = None
    user: UserResponse | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=16, max_length=512)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)


class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)


class StatusMessageResponse(BaseModel):
    status: str
    message: str


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    recovery_codes: list[str]


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class MfaVerifyLoginRequest(BaseModel):
    challenge_token: str = Field(min_length=16, max_length=2048)
    code: str = Field(min_length=6, max_length=16)


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=16)


class SessionInfoResponse(BaseModel):
    id: str
    device_info: str
    ip_address: str | None = None
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime
    is_current: bool = False


class SessionListResponse(BaseModel):
    items: list[SessionInfoResponse]


class SecurityEventResponse(BaseModel):
    id: str
    event_type: str
    severity: str
    summary: str
    ip_address: str | None = None
    created_at: datetime
    alert: bool = False


class SecurityEventListResponse(BaseModel):
    items: list[SecurityEventResponse]


class DataRetentionUpdateRequest(BaseModel):
    retention_days: int = Field(ge=7, le=3650)


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirm_text: str = Field(default="DELETE", max_length=32)


class PrivacyOverviewResponse(BaseModel):
    data_retention_days: int
    gmail_scope: str
    emails_stored: int
    connected_accounts: int
    notifications_stored: int
    encryption_at_rest: str
    limited_use_notice: str


class GoogleConnectResponse(BaseModel):
    authorization_url: str
    state: str
    pkce_enabled: bool = True


class ConnectedAccountResponse(BaseModel):
    id: str
    email_address: EmailStr
    provider: str
    connected_at: datetime
    last_synced_at: datetime | None = None
    sync_status: AccountSyncStatus
    status_message: str | None = None


class ConnectedAccountListResponse(BaseModel):
    items: list[ConnectedAccountResponse]


class EmailResponse(BaseModel):
    id: str
    account_id: str
    gmail_message_id: str
    sender: str
    subject: str
    body_preview: str
    received_at: datetime
    category: EmailCategory
    confidence: float = Field(ge=0.0, le=1.0)
    company_name: str | None = None
    job_role: str | None = None
    is_read: bool = False
    has_attachments: bool = False
    attachment_names: list[str] = Field(default_factory=list)


class EmailListResponse(BaseModel):
    items: list[EmailResponse]
    total: int


class EmailUpdateRequest(BaseModel):
    is_read: bool


class SyncRequest(BaseModel):
    account_id: str | None = None


class SyncResponse(BaseModel):
    status: str
    message: str
    synced_accounts: int = 0
    new_messages: int = 0
    skipped_duplicates: int = 0
    failed_accounts: int = 0


class SyncHistoryItem(BaseModel):
    id: str
    account_id: str
    email_address: str
    started_at: datetime
    finished_at: datetime
    status: str
    new_messages: int = 0
    skipped_duplicates: int = 0
    error_message: str | None = None


class SyncHistoryListResponse(BaseModel):
    items: list[SyncHistoryItem]


class DashboardStatsResponse(BaseModel):
    total_processed_emails: int = 0
    total_job_emails: int = 0
    new_opportunities: int = 0
    interview_invitations: int = 0
    assessment_invitations: int = 0
    unread_count: int = 0
    category_counts: dict[str, int] = Field(default_factory=dict)


class NotificationPreferencesSchema(BaseModel):
    push_enabled: bool = True
    job_opportunities: bool = True
    internship_opportunities: bool = True
    interview_invitations: bool = True
    online_assessments: bool = True
    recruitment_drives: bool = True
    offer_letters: bool = True
    application_updates: bool = False


class NotificationResponse(BaseModel):
    id: str
    email_id: str
    title: str
    message: str
    category: EmailCategory = EmailCategory.JOB
    created_at: datetime
    is_read: bool = False


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]


class NotificationUpdateRequest(BaseModel):
    is_read: bool = True


class DeviceRegisterRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: str = Field(default="unknown", max_length=32)


class ClassificationPredictRequest(BaseModel):
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=20000)
    sender: str = Field(default="", max_length=320)


class ClassificationPredictResponse(BaseModel):
    category: EmailCategory
    confidence: float = Field(ge=0.0, le=1.0)
    company_name: str | None = None
    job_role: str | None = None


class ClassificationFeedbackRequest(BaseModel):
    email_id: str = Field(min_length=1)
    corrected_category: EmailCategory


class ClassificationFeedbackResponse(BaseModel):
    status: str
    email_id: str
    corrected_category: EmailCategory
