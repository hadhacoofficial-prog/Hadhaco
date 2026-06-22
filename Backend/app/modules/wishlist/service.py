import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wishlist.repository import WishlistRepository
from app.modules.wishlist.schemas import (
    AddToWishlistRequest,
    WishlistItemResponse,
    WishlistResponse,
)

_repo = WishlistRepository()


class WishlistService:
    async def get(self, db: AsyncSession, user_id: uuid.UUID) -> WishlistResponse:
        wishlist = await _repo.get_or_create(db, user_id)
        items = [WishlistItemResponse.model_validate(i) for i in wishlist.items]
        return WishlistResponse(id=wishlist.id, items=items, total=len(items))

    async def add(
        self, db: AsyncSession, user_id: uuid.UUID, payload: AddToWishlistRequest
    ) -> WishlistResponse:
        wishlist = await _repo.get_or_create(db, user_id)
        await _repo.add_item(db, wishlist.id, payload.product_id, payload.variant_id)
        return await self.get(db, user_id)

    async def remove(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> WishlistResponse:
        wishlist = await _repo.get_or_create(db, user_id)
        await _repo.remove_item(db, wishlist.id, product_id, variant_id)
        return await self.get(db, user_id)

    async def toggle(
        self, db: AsyncSession, user_id: uuid.UUID, payload: AddToWishlistRequest
    ) -> dict:
        wishlist = await _repo.get_or_create(db, user_id)
        already_in = await _repo.is_in_wishlist(
            db, wishlist.id, payload.product_id, payload.variant_id
        )
        if already_in:
            await _repo.remove_item(db, wishlist.id, payload.product_id, payload.variant_id)
            return {"action": "removed", "product_id": str(payload.product_id)}
        else:
            await _repo.add_item(db, wishlist.id, payload.product_id, payload.variant_id)
            return {"action": "added", "product_id": str(payload.product_id)}
