import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fulfillment.models import FulfillmentTimeline


class FulfillmentTimelineRepository:
    """Repository for fulfillment timeline operations."""

    async def add_entry(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        action: str,
        actor_id: uuid.UUID | None = None,
        admin_name: str | None = None,
        details: dict | None = None,
    ) -> FulfillmentTimeline:
        """Add a fulfillment timeline entry.

        Args:
            db: Database session
            order_id: Order ID
            action: Action performed (e.g., "confirm_payment", "dispatch")
            actor_id: Admin user ID who performed the action
            admin_name: Admin user name (denormalized for easy display)
            details: Additional JSON details about the action

        Returns:
            Created FulfillmentTimeline entry
        """
        entry = FulfillmentTimeline(
            order_id=order_id,
            action=action,
            actor_id=actor_id,
            admin_name=admin_name,
            details=details,
        )
        db.add(entry)
        return entry

    async def get_for_order(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
    ) -> Sequence[FulfillmentTimeline]:
        """Get all fulfillment timeline entries for an order, ordered by creation date (newest first).

        Args:
            db: Database session
            order_id: Order ID

        Returns:
            List of FulfillmentTimeline entries ordered by created_at DESC
        """
        stmt = (
            select(FulfillmentTimeline)
            .where(FulfillmentTimeline.order_id == order_id)
            .order_by(FulfillmentTimeline.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()
