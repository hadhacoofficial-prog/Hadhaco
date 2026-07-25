from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CompanyConfigOut(BaseModel):
    # General
    name: str
    legal_name: str | None = None
    brand_name: str | None = None
    tagline: str | None = None
    description: str | None = None
    website: str | None = None
    domain: str | None = None

    # Logos
    logo_url: str | None = None
    favicon_url: str | None = None
    packing_slip_logo_url: str | None = None
    shipping_label_logo_url: str | None = None

    # Contact
    phone: str | None = None
    alternate_phone: str | None = None
    whatsapp: str | None = None
    support_email: str | None = None
    sales_email: str | None = None

    # Location
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str = Field(max_length=2)

    # Maps
    google_maps_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    # Business
    gstin: str | None = None
    cin: str | None = None
    business_hours: str | None = None

    # Social
    instagram_url: str | None = None
    facebook_url: str | None = None
    youtube_url: str | None = None
    twitter_x_url: str | None = None
    linkedin_url: str | None = None
    pinterest_url: str | None = None

    # SEO
    default_meta_title: str | None = None
    default_meta_description: str | None = None
    organization_description: str | None = None

    # Theme
    theme_color: str | None = None

    class Config:
        from_attributes = True


class CompanyConfigUpdate(BaseModel):
    # General
    name: str | None = None
    legal_name: str | None = None
    brand_name: str | None = None
    tagline: str | None = None
    description: str | None = None
    website: str | None = None
    domain: str | None = None

    # Logos
    logo_url: str | None = None
    favicon_url: str | None = None
    packing_slip_logo_url: str | None = None
    shipping_label_logo_url: str | None = None

    # Contact
    phone: str | None = None
    alternate_phone: str | None = None
    whatsapp: str | None = None
    support_email: str | None = None
    sales_email: str | None = None

    # Location
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = Field(default=None, max_length=2)

    # Maps
    google_maps_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    # Business
    gstin: str | None = None
    cin: str | None = None
    business_hours: str | None = None

    # Social
    instagram_url: str | None = None
    facebook_url: str | None = None
    youtube_url: str | None = None
    twitter_x_url: str | None = None
    linkedin_url: str | None = None
    pinterest_url: str | None = None

    # SEO
    default_meta_title: str | None = None
    default_meta_description: str | None = None
    organization_description: str | None = None

    # Theme
    theme_color: str | None = None

    @field_validator("country")
    @classmethod
    def _uppercase_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v
