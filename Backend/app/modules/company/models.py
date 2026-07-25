from __future__ import annotations

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyConfig(Base):
    __tablename__ = "company_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # ── General ──────────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="Hadha Jewellery"
    )
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Logos ────────────────────────────────────────────────────────────────
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_r2_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    packing_slip_logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_label_logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Contact ──────────────────────────────────────────────────────────────
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(30), nullable=True)
    support_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sales_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Location ─────────────────────────────────────────────────────────────
    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="IN")

    # ── Maps ─────────────────────────────────────────────────────────────────
    google_maps_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Business ─────────────────────────────────────────────────────────────
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cin: Mapped[str | None] = mapped_column(String(30), nullable=True)
    business_hours: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Social ───────────────────────────────────────────────────────────────
    instagram_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    facebook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    twitter_x_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinterest_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── SEO ──────────────────────────────────────────────────────────────────
    default_meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Theme ────────────────────────────────────────────────────────────────
    theme_color: Mapped[str | None] = mapped_column(String(10), nullable=True)
