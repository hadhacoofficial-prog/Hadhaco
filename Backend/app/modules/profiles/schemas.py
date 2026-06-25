import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.constants import UserRole

_PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    phone: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(BaseModel):
    full_name: Annotated[str | None, Field(max_length=100, default=None)]
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _PHONE_RE.match(v):
            raise ValueError("Phone must be in E.164 format, e.g. +919876543210")
        return v


class AdminUserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    phone: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime


class AdminUserRoleUpdateRequest(BaseModel):
    role: UserRole


class AdminUserStatusUpdateRequest(BaseModel):
    is_active: bool


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
