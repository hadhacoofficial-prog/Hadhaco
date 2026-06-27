from __future__ import annotations

from pydantic import BaseModel


class CompanyConfigOut(BaseModel):
    name: str
    tagline: str | None
    gstin: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str
    phone: str | None
    support_email: str | None
    website: str | None
    logo_url: str | None
    instagram_url: str | None
    facebook_url: str | None

    class Config:
        from_attributes = True


class CompanyConfigUpdate(BaseModel):
    name: str | None = None
    tagline: str | None = None
    gstin: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    phone: str | None = None
    support_email: str | None = None
    website: str | None = None
    logo_url: str | None = None
    instagram_url: str | None = None
    facebook_url: str | None = None
