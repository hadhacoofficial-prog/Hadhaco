import math
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.enquiries.repository import EnquiryRepository
from app.modules.enquiries.schemas import (
    EnquiryCreateRequest,
    EnquiryPage,
    EnquiryResponse,
    EnquiryStats,
    EnquiryUpdateRequest,
)

_repo = EnquiryRepository()
log = structlog.get_logger(__name__)

_STATUS_CONTACTED = "contacted_customer"


class EnquiryService:
    async def create(
        self,
        db: AsyncSession,
        payload: EnquiryCreateRequest,
        user_id: uuid.UUID | None = None,
    ) -> EnquiryResponse:
        enquiry = await _repo.create(
            db,
            {
                "user_id": user_id,
                "name": payload.name,
                "email": payload.email.strip().lower(),
                "phone": payload.phone.strip() if payload.phone else None,
                "subject": payload.subject,
                "message": payload.message,
                "status": "new_enquiry",
            },
        )
        log.info(
            "enquiry_created",
            enquiry_id=str(enquiry.id),
            email=enquiry.email,
            has_user=user_id is not None,
        )
        return EnquiryResponse.model_validate(enquiry)

    async def get(self, db: AsyncSession, enquiry_id: uuid.UUID) -> EnquiryResponse:
        enquiry = await _repo.get_by_id(db, enquiry_id)
        if not enquiry:
            raise NotFoundError("Enquiry not found")
        return EnquiryResponse.model_validate(enquiry)

    async def update(
        self,
        db: AsyncSession,
        enquiry_id: uuid.UUID,
        payload: EnquiryUpdateRequest,
    ) -> EnquiryResponse:
        enquiry = await _repo.get_by_id(db, enquiry_id)
        if not enquiry:
            raise NotFoundError("Enquiry not found")

        updates: dict = payload.model_dump(exclude_unset=True)

        if "status" in updates and updates["status"] == _STATUS_CONTACTED:
            if not enquiry.contacted_at:
                updates["contacted_at"] = datetime.now(UTC)

        if updates:
            await _repo.update(db, enquiry_id, updates)

        updated = await _repo.get_by_id(db, enquiry_id)
        assert updated is not None
        return EnquiryResponse.model_validate(updated)

    async def archive(self, db: AsyncSession, enquiry_id: uuid.UUID) -> EnquiryResponse:
        enquiry = await _repo.get_by_id(db, enquiry_id)
        if not enquiry:
            raise NotFoundError("Enquiry not found")
        await _repo.update(db, enquiry_id, {"is_archived": True})
        updated = await _repo.get_by_id(db, enquiry_id)
        assert updated is not None
        return EnquiryResponse.model_validate(updated)

    async def unarchive(
        self, db: AsyncSession, enquiry_id: uuid.UUID
    ) -> EnquiryResponse:
        enquiry = await _repo.get_by_id(db, enquiry_id)
        if not enquiry:
            raise NotFoundError("Enquiry not found")
        await _repo.update(db, enquiry_id, {"is_archived": False})
        updated = await _repo.get_by_id(db, enquiry_id)
        assert updated is not None
        return EnquiryResponse.model_validate(updated)

    async def delete(self, db: AsyncSession, enquiry_id: uuid.UUID) -> None:
        enquiry = await _repo.get_by_id(db, enquiry_id)
        if not enquiry:
            raise NotFoundError("Enquiry not found")
        await _repo.delete(db, enquiry_id)
        log.info("enquiry_deleted", enquiry_id=str(enquiry_id))

    async def list_paginated(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
        include_archived: bool = False,
    ) -> EnquiryPage:
        if status:
            valid = {
                "new_enquiry",
                "contacted_customer",
                "positive_response",
                "negative_response",
                "closed",
            }
            if status not in valid:
                raise ValidationError(f"Invalid status filter: {status}")

        items, total = await _repo.list_paginated(
            db,
            page=page,
            page_size=page_size,
            status=status,
            search=search,
            include_archived=include_archived,
        )

        status_counts = await _repo.get_status_counts(
            db, include_archived=include_archived
        )
        archived_count = await _repo.get_archived_count(db)
        total_pages = math.ceil(total / page_size) if total else 0

        return EnquiryPage(
            items=[EnquiryResponse.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            stats=EnquiryStats(
                total=total,
                new_enquiry=status_counts.get("new_enquiry", 0),
                contacted_customer=status_counts.get("contacted_customer", 0),
                positive_response=status_counts.get("positive_response", 0),
                negative_response=status_counts.get("negative_response", 0),
                closed=status_counts.get("closed", 0),
                archived=archived_count,
            ),
        )
