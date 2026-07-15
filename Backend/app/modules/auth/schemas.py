import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.common.validators import IpAddressStr


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
