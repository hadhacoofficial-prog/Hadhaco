import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Image(Base):
    """
    Canonical image asset — one row per uploaded original, shared by every
    module (product, collection, category, hero, banner, cms_section_item,
    user, review, company_config, seo_page, ...) via owner_type/owner_id.

    See docs/architecture/Universal_Responsive_Image_System_Design.md §9.
    """

    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    preset_id: Mapped[str] = mapped_column(String(60), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    original_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_ext: Mapped[str] = mapped_column(String(10), nullable=False)
    original_width: Mapped[int] = mapped_column(Integer, nullable=False)
    original_height: Mapped[int] = mapped_column(Integer, nullable=False)
    original_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # CropGeometry per breakpoint, focus_point, safe_area snapshot, preset
    # snapshot, generated_variants read-cache — see architecture doc §13.
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ready"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    variants: Mapped[list["ImageVariant"]] = relationship(
        "ImageVariant",
        back_populates="image",
        cascade="all, delete-orphan",
        order_by="ImageVariant.breakpoint, ImageVariant.variant_name, ImageVariant.dpr",
    )


class ImageVariant(Base):
    """One generated derived file (thumbnail/medium/large/hero-desktop@2x/...)."""

    __tablename__ = "image_variants"
    __table_args__ = (
        UniqueConstraint(
            "image_id",
            "breakpoint",
            "variant_name",
            "dpr",
            name="uq_image_variants_image_breakpoint_variant_dpr",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )
    breakpoint: Mapped[str] = mapped_column(String(20), nullable=False)
    variant_name: Mapped[str] = mapped_column(String(40), nullable=False)
    dpr: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    format: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="webp"
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ready"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    image: Mapped["Image"] = relationship("Image", back_populates="variants")
