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


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="delivery_one"
    )
    provider_shipment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    awb_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    label_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    label_r2_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="pending"
    )
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    length_cm: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    width_cm: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    estimated_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)
    pickup_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    events: Mapped[list["ShipmentEvent"]] = relationship(
        "ShipmentEvent",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentEvent.occurred_at.desc()",
        lazy="select",
    )

    __table_args__ = (
        Index("idx_shipments_order_id", "order_id"),
        Index("idx_shipments_awb_number", "awb_number"),
        Index("idx_shipments_status", "status"),
    )


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    shipment: Mapped["Shipment"] = relationship("Shipment", back_populates="events")

    __table_args__ = (Index("idx_shipment_events_shipment_id", "shipment_id"),)
