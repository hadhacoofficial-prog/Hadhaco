import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.wishlist.models import Wishlist, WishlistItem


class WishlistRepository:
    async def get_or_create(self, db: AsyncSession, user_id: uuid.UUID) -> Wishlist:
        result = await db.execute(
            select(Wishlist)
            .where(Wishlist.user_id == user_id)
            .options(selectinload(Wishlist.items))
        )
        wishlist = result.scalar_one_or_none()
        if not wishlist:
            wishlist = Wishlist(id=uuid.uuid4(), user_id=user_id)
            db.add(wishlist)
            await db.flush()
            await db.refresh(wishlist)
            # reload with items relationship
            result = await db.execute(
                select(Wishlist)
                .where(Wishlist.id == wishlist.id)
                .options(selectinload(Wishlist.items))
            )
            wishlist = result.scalar_one()
        return wishlist

    async def add_item(
        self,
        db: AsyncSession,
        wishlist_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> WishlistItem:
        stmt = (
            pg_insert(WishlistItem)
            .values(
                id=uuid.uuid4(),
                wishlist_id=wishlist_id,
                product_id=product_id,
                variant_id=variant_id,
            )
            .on_conflict_do_nothing(constraint="uq_wishlist_items")
        )
        await db.execute(stmt)

        result = await db.execute(
            select(WishlistItem).where(
                WishlistItem.wishlist_id == wishlist_id,
                WishlistItem.product_id == product_id,
                WishlistItem.variant_id == variant_id,
            )
        )
        return result.scalar_one()

    async def remove_item(
        self,
        db: AsyncSession,
        wishlist_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> bool:
        q = delete(WishlistItem).where(
            WishlistItem.wishlist_id == wishlist_id,
            WishlistItem.product_id == product_id,
        )
        if variant_id:
            q = q.where(WishlistItem.variant_id == variant_id)
        else:
            q = q.where(WishlistItem.variant_id.is_(None))
        result = await db.execute(q)
        return result.rowcount > 0

    async def is_in_wishlist(
        self,
        db: AsyncSession,
        wishlist_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> bool:
        q = select(WishlistItem.id).where(
            WishlistItem.wishlist_id == wishlist_id,
            WishlistItem.product_id == product_id,
        )
        if variant_id:
            q = q.where(WishlistItem.variant_id == variant_id)
        else:
            q = q.where(WishlistItem.variant_id.is_(None))
        result = await db.execute(q)
        return result.scalar_one_or_none() is not None
