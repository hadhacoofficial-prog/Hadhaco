from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class DevLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class DevUserPayload(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: str
    full_name: str | None
    first_name: str | None
    last_name: str | None


class DevSessionPayload(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int
    token_type: str


class DevLoginResponse(BaseModel):
    user: DevUserPayload
    session: DevSessionPayload


class DevMeResponse(BaseModel):
    user_id: str
    supabase_uid: str
    email: str | None
    role: str
    is_active: bool
    session_expires_at: datetime | None
    permissions: list[str]
