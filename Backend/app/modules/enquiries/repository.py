import uuid
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enquiries.models import ContactEnquiry


class EnquiryRepository:
    async def get_by_id(
        self, db: AsyncSession, enquiry_id: uuid.UUID
    ) -> ContactEnquiry | None:
        result = await db.execute(
            select(ContactEnquiry).where(ContactEnquiry.id == enquiry_id)
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> ContactEnquiry:
        enquiry = ContactEnquiry(**data)
        db.add(enquiry)
        await db.flush()
        await db.refresh(enquiry)
        return enquiry

    async def update(
        self,
        db: AsyncSession,
        enquiry_id: uuid.UUID,
        data: dict[str, Any],
    ) -> ContactEnquiry | None:
        await db.execute(
            update(ContactEnquiry).where(ContactEnquiry.id == enquiry_id).values(**data)
        )
        return await self.get_by_id(db, enquiry_id)

    async def delete(self, db: AsyncSession, enquiry_id: uuid.UUID) -> bool:
        result = await db.execute(
            sa_delete(ContactEnquiry).where(ContactEnquiry.id == enquiry_id)
        )
        return result.rowcount > 0

    async def list_paginated(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
        include_archived: bool = False,
    ) -> tuple[list[ContactEnquiry], int]:
        filters = []
        if not include_archived:
            filters.append(ContactEnquiry.is_archived == False)  # noqa: E712
        if status:
            filters.append(ContactEnquiry.status == status)
        if search:
            term = f"%{search}%"
            filters.append(
                ContactEnquiry.name.ilike(term)
                | ContactEnquiry.email.ilike(term)
                | ContactEnquiry.subject.ilike(term)
            )

        where_clause = filters[0] if len(filters) == 1 else filters if filters else None

        count_q = select(func.count()).select_from(ContactEnquiry)
        if where_clause is not None:
            count_q = count_q.where(*filters)
        total = (await db.execute(count_q)).scalar_one()

        q = select(ContactEnquiry)
        if where_clause is not None:
            q = q.where(*filters)
        q = (
            q.order_by(ContactEnquiry.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await db.execute(q)).scalars().all())
        return items, total

    async def get_status_counts(
        self, db: AsyncSession, *, include_archived: bool = False
    ) -> dict[str, int]:
        base_filter = []
        if not include_archived:
            base_filter.append(ContactEnquiry.is_archived == False)  # noqa: E712

        q = select(
            ContactEnquiry.status,
            func.count(ContactEnquiry.id),
        ).group_by(ContactEnquiry.status)
        if base_filter:
            q = q.where(*base_filter)

        result = await db.execute(q)
        return {row[0]: row[1] for row in result.all()}

    async def get_archived_count(self, db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(ContactEnquiry)
            .where(ContactEnquiry.is_archived == True)  # noqa: E712
        )
        return result.scalar_one()
