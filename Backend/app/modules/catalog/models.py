import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.categories.models import Category
    from app.modules.media.models import Image


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Jewellery-specific
    metal_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    purity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hallmark_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    weight_grams: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    making_charges: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    wastage_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Pricing
    base_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    compare_at_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    cost_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_rate: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default="3.0"
    )
    hsn_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Inventory
    track_inventory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    allow_backorder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    low_stock_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="5"
    )
    stock_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reserved_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    sold_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    max_order_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    # Status / flags
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_new_arrival: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_best_seller: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_customizable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    requires_shipping: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    # Dimensions (for shipping)
    length_cm: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    width_cm: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    # SEO
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meta_keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Cached review aggregates (recalculated on approve/reject/delete)
    average_rating: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    # Full-text search vector (populated by DB trigger)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    category: Mapped["Category | None"] = relationship(  # noqa: F821
        "Category", foreign_keys=[category_id], lazy="select"
    )
    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="select",
    )
    # Polymorphic, read-only: the universal images table's owner_type='product'
    # rows for this product. Writes go through ImageRepository/
    # UniversalImageService (app.modules.media), not this relationship — see
    # docs/architecture/Universal_Responsive_Image_System_Design.md §9.
    images: Mapped[list["Image"]] = relationship(
        "Image",
        primaryjoin=(
            "and_(foreign(Image.owner_id)==Product.id, "
            "Image.owner_type=='product', Image.deleted_at==None)"
        ),
        order_by="Image.sort_order",
        viewonly=True,
        lazy="select",
    )
    attributes: Mapped[list["ProductAttribute"]] = relationship(
        "ProductAttribute",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="select",
    )

    __table_args__ = (
        Index("idx_products_slug", "slug"),
        Index("idx_products_sku", "sku"),
        Index("idx_products_category_id", "category_id"),
        Index("idx_products_status", "status"),
        Index("idx_products_deleted_at", "deleted_at"),
        Index("idx_products_is_featured", "is_featured"),
        Index("idx_products_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "idx_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "idx_products_sku_trgm",
            "sku",
            postgresql_using="gin",
            postgresql_ops={"sku": "gin_trgm_ops"},
        ),
        CheckConstraint(
            "gender IS NULL OR gender IN ('women','men','kids','unisex')",
            name="products_gender_check",
        ),
        CheckConstraint("base_price > 0", name="products_base_price_check"),
        CheckConstraint("stock_quantity >= 0", name="products_stock_quantity_check"),
        CheckConstraint(
            "reserved_quantity >= 0", name="products_reserved_quantity_check"
        ),
        CheckConstraint("sold_quantity >= 0", name="products_sold_quantity_check"),
        CheckConstraint(
            "status IN ('draft','active','archived')", name="products_status_check"
        ),
    )

    @property
    def available_stock(self) -> int:
        active_variants = [variant for variant in self.variants if variant.is_active]
        if active_variants:
            return sum(variant.available_stock for variant in active_variants)
        return max(self.stock_quantity - self.reserved_quantity - self.sold_quantity, 0)


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_adjustment: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    stock_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reserved_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    sold_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    weight_grams: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped["Product"] = relationship("Product", back_populates="variants")

    __table_args__ = (
        Index("idx_product_variants_product_id", "product_id"),
        Index("idx_product_variants_sku", "sku"),
        CheckConstraint(
            "stock_quantity >= 0", name="product_variants_stock_quantity_check"
        ),
        CheckConstraint(
            "reserved_quantity >= 0", name="product_variants_reserved_quantity_check"
        ),
        CheckConstraint(
            "sold_quantity >= 0", name="product_variants_sold_quantity_check"
        ),
    )

    @property
    def available_stock(self) -> int:
        return max(self.stock_quantity - self.reserved_quantity - self.sold_quantity, 0)


class ProductAttribute(Base):
    __tablename__ = "product_attributes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    product: Mapped["Product"] = relationship("Product", back_populates="attributes")

    __table_args__ = (
        Index("idx_product_attributes_product_id", "product_id"),
        UniqueConstraint(
            "product_id", "name", name="uq_product_attributes_product_name"
        ),
    )
