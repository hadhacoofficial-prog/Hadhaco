from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyConfig(Base):
    __tablename__ = "company_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="Hadha Jewellery"
    )
    tagline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="IN")
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    support_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_r2_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    packing_slip_logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_label_logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    facebook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
