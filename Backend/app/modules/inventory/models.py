import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    movement_type: Mapped[str] = mapped_column(
        ENUM(
            "purchase",
            "sale",
            "return",
            "adjustment",
            "damage",
            "transfer",
            "correction",
            name="inventory_movement_type",
            create_type=False,
        ),
        nullable=False,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_inventory_movements_product_id", "product_id"),
        Index("idx_inventory_movements_variant_id", "variant_id"),
        Index("idx_inventory_movements_movement_type", "movement_type"),
        Index("idx_inventory_movements_reference", "reference_type", "reference_id"),
        Index("idx_inventory_movements_created_at", "created_at"),
        Index("idx_inventory_movements_created_by", "created_by"),
    )


class InventoryReservation(Base):
    """
    Tracks stock held for a pending checkout.
    Status flow: ACTIVE → COMPLETED (payment success) | RELEASED (failure/cancel) | EXPIRED (timeout).
    reserved_quantity on products is decremented when leaving ACTIVE.
    """

    __tablename__ = "inventory_reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reservation_number: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        ENUM(
            "ACTIVE",
            "COMPLETED",
            "RELEASED",
            "EXPIRED",
            name="inventory_reservation_status",
            create_type=False,
        ),
        nullable=False,
        server_default="ACTIVE",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
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

    __table_args__ = (
        Index("idx_inv_res_user_id", "user_id"),
        Index("idx_inv_res_order_id", "order_id"),
        Index("idx_inv_res_product_id", "product_id"),
        Index("idx_inv_res_status", "status"),
        Index("idx_inv_res_expires_at", "expires_at"),
        Index("idx_inv_res_status_expires", "status", "expires_at"),
        Index("idx_inv_res_variant_id", "variant_id"),
    )


class InventoryTransaction(Base):
    """
    Immutable audit log for every inventory state change.
    before/after_available = stock_quantity - reserved_quantity - sold_quantity.
    """

    __tablename__ = "inventory_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_reservations.id", ondelete="SET NULL"),
        nullable=True,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    transaction_type: Mapped[str] = mapped_column(
        ENUM(
            "RESERVE",
            "RELEASE",
            "SALE",
            "RETURN",
            "RESTOCK",
            "ADJUSTMENT",
            name="inventory_transaction_type",
            create_type=False,
        ),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    before_available: Mapped[int] = mapped_column(Integer, nullable=False)
    after_available: Mapped[int] = mapped_column(Integer, nullable=False)
    before_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    after_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    before_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    after_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_inv_txn_product_id", "product_id"),
        Index("idx_inv_txn_reservation_id", "reservation_id"),
        Index("idx_inv_txn_order_id", "order_id"),
        Index("idx_inv_txn_type", "transaction_type"),
        Index("idx_inv_txn_created_at", "created_at"),
    )
