import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.sequences import next_sequence_value
from app.modules.orders.models import Order, OrderItem


class OrderRepository:
    def _with_items(self):
        return selectinload(Order.items)

    async def get_by_id(self, db: AsyncSession, order_id: uuid.UUID) -> Order | None:
        result = await db.execute(
            select(Order).where(Order.id == order_id).options(self._with_items())
        )
        return result.scalar_one_or_none()

    async def get_by_order_number(
        self, db: AsyncSession, order_number: str
    ) -> Order | None:
        result = await db.execute(
            select(Order)
            .where(Order.order_number == order_number)
            .options(self._with_items())
        )
        return result.scalar_one_or_none()

    async def get_by_razorpay_order_id(
        self, db: AsyncSession, razorpay_order_id: str
    ) -> Order | None:
        result = await db.execute(
            select(Order)
            .where(Order.razorpay_order_id == razorpay_order_id)
            .options(self._with_items())
        )
        return result.scalar_one_or_none()

    async def get_by_ids(
        self, db: AsyncSession, order_ids: list[uuid.UUID]
    ) -> list[Order]:
        """Batch-load orders by a list of IDs in a single query.

        Returns only orders that exist — missing IDs are silently omitted.
        """
        if not order_ids:
            return []
        result = await db.execute(
            select(Order).where(Order.id.in_(order_ids)).options(self._with_items())
        )
        return list(result.scalars().all())

    @staticmethod
    def _item_count_subquery():
        """Correlated scalar subquery that returns ORDER item count without loading rows."""
        return (
            select(func.count(OrderItem.id))
            .where(OrderItem.order_id == Order.id)
            .correlate(Order)
            .scalar_subquery()
        )

    async def list_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 10,
        status: str | None = None,
    ) -> tuple[list[Order], int]:
        item_count_sq = self._item_count_subquery()

        q = select(Order, item_count_sq.label("_item_count")).where(
            Order.user_id == user_id
        )
        count_q = select(func.count(Order.id)).where(Order.user_id == user_id)

        if status:
            q = q.where(Order.status == status)
            count_q = count_q.where(Order.status == status)

        total = (await db.execute(count_q)).scalar_one()

        q = (
            q.order_by(Order.created_at.desc(), Order.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)

        orders: list[Order] = []
        for order_obj, item_count in result.all():
            order_obj._item_count = item_count
            orders.append(order_obj)
        return orders, total

    # Allowlisted admin sort keys -> columns (never getattr on user input).
    _ADMIN_SORT_COLUMNS: dict[str, Any] = {
        "created_at": Order.created_at,
        "total": Order.total,
        "order_number": Order.order_number,
        "status": Order.status,
        "payment_status": Order.payment_status,
        "fulfillment_status": Order.fulfillment_status,
        "customer": func.lower(Order.shipping_full_name),
    }

    async def list_all(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        payment_status: str | None = None,
        user_id: uuid.UUID | None = None,
        search: str | None = None,
        fulfillment_status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_total: float | None = None,
        max_total: float | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> tuple[list[Order], int]:
        item_count_sq = self._item_count_subquery()

        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(Order.status == status)
        if payment_status:
            filters.append(Order.payment_status == payment_status)
        if fulfillment_status:
            filters.append(Order.fulfillment_status == fulfillment_status)
        if user_id:
            filters.append(Order.user_id == user_id)
        if date_from is not None:
            filters.append(Order.created_at >= date_from)
        if date_to is not None:
            filters.append(Order.created_at < date_to)
        if min_total is not None:
            filters.append(Order.total >= min_total)
        if max_total is not None:
            filters.append(Order.total <= max_total)
        if search:
            from app.modules.profiles.models import Profile

            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Order.order_number.ilike(term),
                    Order.shipping_full_name.ilike(term),
                    Order.shipping_phone.ilike(term),
                    Order.user_id.in_(
                        select(Profile.id).where(Profile.email.ilike(term))
                    ),
                )
            )

        count_q = select(func.count(Order.id)).where(*filters)
        total = (await db.execute(count_q)).scalar_one()

        col = self._ADMIN_SORT_COLUMNS.get(sort_by, Order.created_at)
        order = col.desc() if sort_dir == "desc" else col.asc()
        q = (
            select(Order, item_count_sq.label("_item_count"))
            .where(*filters)
            # id tie-breaker keeps offset pages stable when sort values tie.
            .order_by(order, Order.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)

        orders: list[Order] = []
        for order_obj, item_count in result.all():
            order_obj._item_count = item_count
            orders.append(order_obj)
        return orders, total

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Order:
        order = Order(**data)
        db.add(order)
        await db.flush()
        await db.refresh(order)
        return order

    async def add_item(self, db: AsyncSession, data: dict[str, Any]) -> OrderItem:
        item = OrderItem(**data)
        db.add(item)
        await db.flush()
        return item

    async def update(
        self, db: AsyncSession, order_id: uuid.UUID, data: dict[str, Any]
    ) -> Order | None:
        await db.execute(update(Order).where(Order.id == order_id).values(**data))
        return await self.get_by_id(db, order_id)

    async def generate_order_number(self, db: AsyncSession) -> str:
        """Generate sequential order number: HDH-YYYYMM-NNNNNN"""
        from datetime import datetime

        now = datetime.now(UTC)
        prefix = f"HDH-{now.year}{now.month:02d}-"
        seq = await next_sequence_value(db, f"order_number:{prefix}")
        return f"{prefix}{seq:06d}"
