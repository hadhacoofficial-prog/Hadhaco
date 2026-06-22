import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Invoice, Payment, Refund


class PaymentRepository:
    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Payment:
        p = Payment(**data)
        db.add(p)
        await db.flush()
        await db.refresh(p)
        return p

    async def get_by_id(self, db: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
        result = await db.execute(select(Payment).where(Payment.id == payment_id))
        return result.scalar_one_or_none()

    async def get_by_razorpay_order_id(self, db: AsyncSession, rzp_order_id: str) -> Payment | None:
        result = await db.execute(select(Payment).where(Payment.razorpay_order_id == rzp_order_id))
        return result.scalar_one_or_none()

    async def get_for_order(self, db: AsyncSession, order_id: uuid.UUID) -> Payment | None:
        result = await db.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update(
        self, db: AsyncSession, payment_id: uuid.UUID, data: dict[str, Any]
    ) -> Payment | None:
        await db.execute(update(Payment).where(Payment.id == payment_id).values(**data))
        return await self.get_by_id(db, payment_id)

    async def create_refund(self, db: AsyncSession, data: dict[str, Any]) -> Refund:
        r = Refund(**data)
        db.add(r)
        await db.flush()
        await db.refresh(r)
        return r

    async def update_refund(
        self, db: AsyncSession, refund_id: uuid.UUID, data: dict[str, Any]
    ) -> Refund | None:
        await db.execute(update(Refund).where(Refund.id == refund_id).values(**data))
        result = await db.execute(select(Refund).where(Refund.id == refund_id))
        return result.scalar_one_or_none()

    async def get_refunds_for_order(self, db: AsyncSession, order_id: uuid.UUID) -> list[Refund]:
        result = await db.execute(
            select(Refund).where(Refund.order_id == order_id).order_by(Refund.created_at.desc())
        )
        return list(result.scalars().all())

    # ── Invoice ──────────────────────────────────────────────────────────────

    async def create_invoice(self, db: AsyncSession, data: dict[str, Any]) -> Invoice:
        inv = Invoice(**data)
        db.add(inv)
        await db.flush()
        await db.refresh(inv)
        return inv

    async def get_invoice_for_order(self, db: AsyncSession, order_id: uuid.UUID) -> Invoice | None:
        result = await db.execute(select(Invoice).where(Invoice.order_id == order_id))
        return result.scalar_one_or_none()

    async def generate_invoice_number(self, db: AsyncSession) -> str:
        from datetime import datetime

        from sqlalchemy import func

        now = datetime.now(UTC)
        prefix = f"INV-{now.year}{now.month:02d}-"
        count_result = await db.execute(
            select(func.count(Invoice.id)).where(Invoice.invoice_number.like(f"{prefix}%"))
        )
        seq = count_result.scalar_one() + 1
        return f"{prefix}{seq:06d}"
