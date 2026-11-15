import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.common.validators import IpAddressStr
from app.core.security import PASSWORD_MAX_BYTES


class VerifyTokenResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: str
    is_active: bool
    avatar_url: str | None


class Setup2FAResponse(BaseModel):
    totp_uri: str
    secret: str
    qr_code_data_url: str


class Verify2FARequest(BaseModel):
    totp_code: str


class Verify2FAResponse(BaseModel):
    message: str
    backup_codes: list[str]


class Validate2FARequest(BaseModel):
    totp_code: str


class Validate2FAResponse(BaseModel):
    valid: bool


class LogoutResponse(BaseModel):
    message: str


class TwoFactorStatusResponse(BaseModel):
    is_enabled: bool
    enabled_at: datetime | None
    backup_codes_remaining: int
    total_backup_codes: int


class Disable2FARequest(BaseModel):
    totp_code: str


class RegenerateBackupCodesRequest(BaseModel):
    totp_code: str


class RegenerateBackupCodesResponse(BaseModel):
    message: str
    backup_codes: list[str]


class AdminSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ip_address: IpAddressStr
    user_agent: str | None
    is_2fa_verified: bool
    verified_at: datetime | None
    expires_at: datetime | None
    last_activity_at: datetime | None
    last_seen_ip: IpAddressStr | None
    last_seen_user_agent: str | None
    device_name: str | None
    browser_name: str | None
    os_name: str | None
    created_at: datetime
    is_current: bool = False


class AdminSessionListResponse(BaseModel):
    sessions: list[AdminSessionOut]


class RevokeSessionResponse(BaseModel):
    revoked_count: int


# ── First-party auth (login / registration / recovery) ───────────────────────

MIN_PASSWORD_LENGTH = 8


def _validate_new_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    # bcrypt reads only the first 72 bytes; reject rather than silently truncate.
    if len(value.encode()) > PASSWORD_MAX_BYTES:
        raise ValueError("Password is too long")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = Field(default=None, max_length=120)

    _check_password = field_validator("password")(_validate_new_password)


class LoginRequest(BaseModel):
    email: EmailStr
    # Not length-checked: existing accounts predate the current policy.
    password: str = Field(min_length=1, max_length=256)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailRequest(BaseModel):
    """Body for "resend verification" and "forgot password"."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str

    _check_password = field_validator("new_password")(_validate_new_password)


class ChangePasswordRequest(BaseModel):
    # Omitted by accounts that signed up with Google and have no password yet.
    current_password: str | None = Field(default=None, max_length=256)
    new_password: str

    _check_password = field_validator("new_password")(_validate_new_password)


class SessionUser(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_verified: bool
    created_at: datetime | None = None


class SessionResponse(BaseModel):
    """Returned by login / refresh / session. The tokens themselves live only
    in HttpOnly cookies; `csrf_token` must be echoed as `X-CSRF-Token` on
    unsafe requests."""

    user: SessionUser
    csrf_token: str
    expires_in: int
    has_password: bool


class RegisterResponse(BaseModel):
    email: str
    verification_required: bool = True
