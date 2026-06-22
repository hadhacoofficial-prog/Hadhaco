import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_customer
from app.modules.addresses.schemas import (
    AddressCreateRequest,
    AddressResponse,
    AddressUpdateRequest,
)
from app.modules.addresses.service import AddressService
from app.modules.profiles.models import Profile

router = APIRouter()
_service = AddressService()


@router.get(
    "/me/addresses",
    response_model=BaseSuccessResponse[list[AddressResponse]],
    dependencies=[Depends(require_customer)],
)
async def list_addresses(
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.list(db, current_user.id)
    return ok(result, ResponseCode.ADDRESS_LISTED, "Addresses fetched successfully")


@router.post(
    "/me/addresses",
    response_model=BaseSuccessResponse[AddressResponse],
    status_code=201,
    dependencies=[Depends(require_customer)],
)
async def create_address(
    payload: AddressCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.create(db, current_user.id, payload)
    return ok(result, ResponseCode.ADDRESS_CREATED, "Address created successfully")


@router.patch(
    "/me/addresses/{address_id}",
    response_model=BaseSuccessResponse[AddressResponse],
    dependencies=[Depends(require_customer)],
)
async def update_address(
    address_id: uuid.UUID,
    payload: AddressUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.update(db, current_user.id, address_id, payload)
    return ok(result, ResponseCode.ADDRESS_UPDATED, "Address updated successfully")


@router.post(
    "/me/addresses/{address_id}/default",
    response_model=BaseSuccessResponse[AddressResponse],
    dependencies=[Depends(require_customer)],
)
async def set_default_address(
    address_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.set_default(db, current_user.id, address_id)
    return ok(
        result, ResponseCode.ADDRESS_DEFAULT_SET, "Default address set successfully"
    )


@router.delete(
    "/me/addresses/{address_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_customer)],
)
async def delete_address(
    address_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    await _service.delete(db, current_user.id, address_id)
    return deleted(ResponseCode.ADDRESS_DELETED, "Address deleted successfully")
