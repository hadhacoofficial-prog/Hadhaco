from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CompanyConfigOut(BaseModel):
    name: str
    tagline: str | None
    gstin: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str = Field(max_length=2)
    phone: str | None
    support_email: str | None
    website: str | None
    logo_url: str | None
    packing_slip_logo_url: str | None
    shipping_label_logo_url: str | None
    instagram_url: str | None
    facebook_url: str | None

    class Config:
        from_attributes = True


class CompanyConfigUpdate(BaseModel):
    name: str | None = None
    tagline: str | None = None
    gstin: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = Field(default=None, max_length=2)
    phone: str | None = None
    support_email: str | None = None
    website: str | None = None
    logo_url: str | None = None
    packing_slip_logo_url: str | None = None
    shipping_label_logo_url: str | None = None
    instagram_url: str | None = None
    facebook_url: str | None = None

    @field_validator("country")
    @classmethod
    def _uppercase_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v
