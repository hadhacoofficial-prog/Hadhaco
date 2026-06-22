import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AddressCreateRequest(BaseModel):
    type: str = Field(default="shipping", pattern="^(shipping|billing)$")
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=20)
    line1: str = Field(..., min_length=1, max_length=255)
    line2: str | None = Field(None, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    postal_code: str = Field(..., min_length=1, max_length=20)
    country: str = Field(default="IN", min_length=2, max_length=2)
    is_default: bool = False

    @field_validator("country")
    @classmethod
    def upper_country(cls, v: str) -> str:
        return v.upper()


class AddressUpdateRequest(BaseModel):
    type: str | None = Field(None, pattern="^(shipping|billing)$")
    full_name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=20)
    line1: str | None = Field(None, min_length=1, max_length=255)
    line2: str | None = None
    city: str | None = Field(None, min_length=1, max_length=100)
    state: str | None = Field(None, min_length=1, max_length=100)
    postal_code: str | None = Field(None, min_length=1, max_length=20)
    country: str | None = Field(None, min_length=2, max_length=2)
    is_default: bool | None = None


class AddressResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    full_name: str
    phone: str | None
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
