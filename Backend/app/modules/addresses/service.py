import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.addresses.repository import _MAX_ADDRESSES, AddressRepository
from app.modules.addresses.schemas import (
    AddressCreateRequest,
    AddressResponse,
    AddressUpdateRequest,
)

_repo = AddressRepository()


class AddressService:
    async def list(self, db: AsyncSession, user_id: uuid.UUID) -> list[AddressResponse]:
        addrs = await _repo.list_for_user(db, user_id)
        return [AddressResponse.model_validate(a) for a in addrs]

    async def create(
        self, db: AsyncSession, user_id: uuid.UUID, payload: AddressCreateRequest
    ) -> AddressResponse:
        count = await _repo.count_for_user(db, user_id)
        if count >= _MAX_ADDRESSES:
            raise ConflictError(
                f"Maximum {_MAX_ADDRESSES} addresses allowed per account"
            )

        if payload.is_default:
            await _repo.clear_default(db, user_id, payload.type)

        data = payload.model_dump()
        data["id"] = uuid.uuid4()
        data["user_id"] = user_id

        addr = await _repo.create(db, data)
        return AddressResponse.model_validate(addr)

    async def update(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        address_id: uuid.UUID,
        payload: AddressUpdateRequest,
    ) -> AddressResponse:
        existing = await _repo.get(db, address_id, user_id)
        if not existing:
            raise NotFoundError("Address not found")

        data = payload.model_dump(exclude_unset=True)

        if data.get("is_default") is True:
            addr_type = data.get("type", existing.type)
            await _repo.clear_default(db, user_id, addr_type)

        addr = await _repo.update(db, address_id, data)
        return AddressResponse.model_validate(addr)

    async def set_default(
        self, db: AsyncSession, user_id: uuid.UUID, address_id: uuid.UUID
    ) -> AddressResponse:
        existing = await _repo.get(db, address_id, user_id)
        if not existing:
            raise NotFoundError("Address not found")
        await _repo.clear_default(db, user_id, existing.type)
        addr = await _repo.update(db, address_id, {"is_default": True})
        return AddressResponse.model_validate(addr)

    async def delete(
        self, db: AsyncSession, user_id: uuid.UUID, address_id: uuid.UUID
    ) -> None:
        existing = await _repo.get(db, address_id, user_id)
        if not existing:
            raise NotFoundError("Address not found")
        await _repo.soft_delete(db, address_id)
