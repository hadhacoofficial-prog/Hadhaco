import uuid
from datetime import datetime

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    coupon_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="percentage"
    )
    value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # ── Status (active / inactive / draft) ────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="active"
    )
    # Kept for backward-compat; new code should use status
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    # ── Validity window ───────────────────────────────────────────────────────
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Order-value constraints ───────────────────────────────────────────────
    min_order_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    max_order_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # ── Discount caps ─────────────────────────────────────────────────────────
    max_discount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # ── Usage limits ──────────────────────────────────────────────────────────
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    per_user_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    one_time_per_customer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # ── Customer eligibility ──────────────────────────────────────────────────
    first_order_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    new_customer_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    returning_customer_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # ── Product / category restrictions (JSONB lists) ─────────────────────────
    eligible_product_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    eligible_collection_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    eligible_category_slugs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    excluded_product_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    excluded_category_slugs: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Audience restrictions ─────────────────────────────────────────────────
    allowed_emails: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    allowed_phone_numbers: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    customer_groups: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Region restrictions ───────────────────────────────────────────────────
    allowed_states: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    allowed_cities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    allowed_pincodes: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Method restrictions ───────────────────────────────────────────────────
    allowed_payment_methods: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    allowed_shipping_methods: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Campaign & stacking ───────────────────────────────────────────────────
    stackable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    campaign_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_coupons_code", "code"),
        Index("idx_coupons_is_active", "is_active"),
        Index("idx_coupons_status", "status"),
        Index("idx_coupons_campaign", "campaign_name"),
        CheckConstraint("value > 0", name="coupons_value_positive"),
        CheckConstraint(
            "coupon_type IN ('percentage','fixed_amount','free_shipping')",
            name="coupons_type_check",
        ),
        CheckConstraint(
            "status IN ('active','inactive','draft')",
            name="coupons_status_check",
        ),
    )


class CouponUsage(Base):
    __tablename__ = "coupon_usages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    coupon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    discount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_coupon_usages_coupon_id", "coupon_id"),
        Index("idx_coupon_usages_user_id", "user_id"),
        UniqueConstraint("coupon_id", "order_id", name="uq_coupon_usage_order"),
    )
