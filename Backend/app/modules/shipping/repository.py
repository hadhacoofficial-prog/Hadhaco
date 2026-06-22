import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.shipping.models import Shipment, ShipmentEvent


class ShipmentRepository:
    async def get_for_order(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> Shipment | None:
        result = await db.execute(
            select(Shipment)
            .where(Shipment.order_id == order_id)
            .options(selectinload(Shipment.events))
        )
        return result.scalar_one_or_none()

    async def get_by_id(
        self, db: AsyncSession, shipment_id: uuid.UUID
    ) -> Shipment | None:
        result = await db.execute(
            select(Shipment)
            .where(Shipment.id == shipment_id)
            .options(selectinload(Shipment.events))
        )
        return result.scalar_one_or_none()

    async def get_by_awb(self, db: AsyncSession, awb_number: str) -> Shipment | None:
        result = await db.execute(
            select(Shipment)
            .where(Shipment.awb_number == awb_number)
            .options(selectinload(Shipment.events))
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Shipment:
        shipment = Shipment(**data)
        db.add(shipment)
        await db.flush()
        await db.refresh(shipment)
        return shipment

    async def update(
        self, db: AsyncSession, shipment_id: uuid.UUID, data: dict[str, Any]
    ) -> Shipment | None:
        await db.execute(
            update(Shipment).where(Shipment.id == shipment_id).values(**data)
        )
        return await self.get_by_id(db, shipment_id)

    async def add_event(self, db: AsyncSession, data: dict[str, Any]) -> ShipmentEvent:
        event = ShipmentEvent(**data)
        db.add(event)
        await db.flush()
        return event

    async def list_active(self, db: AsyncSession) -> list[Shipment]:
        """Return shipments in transit for polling."""
        result = await db.execute(
            select(Shipment).where(
                Shipment.status.in_(
                    ["created", "picked_up", "in_transit", "out_for_delivery"]
                )
            )
        )
        return list(result.scalars().all())
