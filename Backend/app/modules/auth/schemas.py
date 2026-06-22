import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


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


class AdminSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ip_address: str
    user_agent: str | None
    location: str | None
    is_active: bool
    last_seen_at: datetime
    created_at: datetime
