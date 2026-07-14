import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, created, deleted, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user_optional, require_admin
from app.middleware.rate_limit import rate_limit_enquiry
from app.modules.enquiries.schemas import (
    EnquiryCreateRequest,
    EnquiryPage,
    EnquiryResponse,
    EnquiryUpdateRequest,
)
from app.modules.enquiries.service import EnquiryService
from app.modules.profiles.models import Profile

router = APIRouter()
_service = EnquiryService()


@router.post(
    "/enquiries",
    response_model=BaseSuccessResponse[EnquiryResponse],
    status_code=201,
    dependencies=[Depends(rate_limit_enquiry)],
)
async def create_enquiry(
    payload: EnquiryCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Profile | None = Depends(get_current_user_optional),
):
    if payload.website:
        now = datetime.now(UTC)
        return created(
            EnquiryResponse(
                id=uuid.uuid4(),
                user_id=None,
                name="",
                email="",
                phone=None,
                subject="",
                message="",
                status="new_enquiry",
                admin_notes=None,
                contacted_at=None,
                is_archived=False,
                created_at=now,
                updated_at=now,
            ),
            ResponseCode.ENQUIRY_CREATED,
            "Enquiry submitted successfully",
        )

    user_id = current_user.id if current_user else None
    result = await _service.create(db, payload, user_id=user_id)
    return created(
        result, ResponseCode.ENQUIRY_CREATED, "Enquiry submitted successfully"
    )


@router.get(
    "/admin/enquiries",
    response_model=BaseSuccessResponse[EnquiryPage],
    dependencies=[Depends(require_admin)],
)
async def list_enquiries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    search: str | None = Query(None),
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    result = await _service.list_paginated(
        db,
        page=page,
        page_size=page_size,
        status=status,
        search=search,
        include_archived=include_archived,
    )
    return ok(result, ResponseCode.ENQUIRY_LISTED, "Enquiries listed successfully")


@router.get(
    "/admin/enquiries/{enquiry_id}",
    response_model=BaseSuccessResponse[EnquiryResponse],
    dependencies=[Depends(require_admin)],
)
async def get_enquiry(
    enquiry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.get(db, enquiry_id)
    return ok(result, ResponseCode.ENQUIRY_FETCHED, "Enquiry fetched successfully")


@router.patch(
    "/admin/enquiries/{enquiry_id}",
    response_model=BaseSuccessResponse[EnquiryResponse],
    dependencies=[Depends(require_admin)],
)
async def update_enquiry(
    enquiry_id: uuid.UUID,
    payload: EnquiryUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.update(db, enquiry_id, payload)
    return ok(result, ResponseCode.ENQUIRY_UPDATED, "Enquiry updated successfully")


@router.post(
    "/admin/enquiries/{enquiry_id}/archive",
    response_model=BaseSuccessResponse[EnquiryResponse],
    dependencies=[Depends(require_admin)],
)
async def archive_enquiry(
    enquiry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.archive(db, enquiry_id)
    return ok(result, ResponseCode.ENQUIRY_UPDATED, "Enquiry archived successfully")


@router.post(
    "/admin/enquiries/{enquiry_id}/unarchive",
    response_model=BaseSuccessResponse[EnquiryResponse],
    dependencies=[Depends(require_admin)],
)
async def unarchive_enquiry(
    enquiry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.unarchive(db, enquiry_id)
    return ok(result, ResponseCode.ENQUIRY_UPDATED, "Enquiry restored successfully")


@router.delete(
    "/admin/enquiries/{enquiry_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_enquiry(
    enquiry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _service.delete(db, enquiry_id)
    return deleted(ResponseCode.ENQUIRY_DELETED, "Enquiry deleted successfully")
