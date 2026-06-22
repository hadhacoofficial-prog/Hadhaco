import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )

    # Shipping address snapshot
    shipping_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shipping_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_city: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_state: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_postal: Mapped[str] = mapped_column(String(20), nullable=False)
    shipping_country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="IN")

    # Billing address snapshot (optional — defaults to shipping)
    billing_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    billing_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    billing_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    billing_postal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    billing_country: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Financials
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    shipping_charge: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    discount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # Coupon
    coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    coupon_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coupons.id", ondelete="SET NULL"), nullable=True
    )

    # Payment
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Shipping
    shipping_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estimated_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="select"
    )

    __table_args__ = (
        Index("idx_orders_user_id", "user_id"),
        Index("idx_orders_order_number", "order_number"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_payment_status", "payment_status"),
        Index("idx_orders_created_at", "created_at"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )

    # Snapshots
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_sku: Mapped[str] = mapped_column(String(100), nullable=False)
    variant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="3.0")
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    order: Mapped["Order"] = relationship("Order", back_populates="items")

    __table_args__ = (
        Index("idx_order_items_order_id", "order_id"),
        Index("idx_order_items_product_id", "product_id"),
    )
