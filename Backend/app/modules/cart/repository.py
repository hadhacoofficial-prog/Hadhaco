import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.cart.models import Cart, CartItem

_CART_TTL_DAYS = 30
_AUTHENTICATED_CART_TTL_DAYS = 90


class CartRepository:
    def _expiry(self, authenticated: bool = False) -> datetime:
        days = _AUTHENTICATED_CART_TTL_DAYS if authenticated else _CART_TTL_DAYS
        return datetime.now(UTC) + timedelta(days=days)

    async def get_for_user(self, db: AsyncSession, user_id: uuid.UUID) -> Cart | None:
        now = datetime.now(UTC)
        result = await db.execute(
            select(Cart)
            .where(Cart.user_id == user_id, Cart.expires_at > now)
            .options(selectinload(Cart.items))
            .order_by(Cart.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_session(self, db: AsyncSession, session_id: str) -> Cart | None:
        now = datetime.now(UTC)
        result = await db.execute(
            select(Cart)
            .where(Cart.session_id == session_id, Cart.expires_at > now)
            .options(selectinload(Cart.items))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, cart_id: uuid.UUID) -> Cart | None:
        result = await db.execute(
            select(Cart).where(Cart.id == cart_id).options(selectinload(Cart.items))
        )
        return result.scalar_one_or_none()

    async def create(
        self, db: AsyncSession, user_id: uuid.UUID | None, session_id: str | None
    ) -> Cart:
        cart = Cart(
            id=uuid.uuid4(),
            user_id=user_id,
            session_id=session_id,
            expires_at=self._expiry(authenticated=user_id is not None),
        )
        db.add(cart)
        await db.flush()
        await db.refresh(cart)
        return cart

    async def upsert_item(
        self,
        db: AsyncSession,
        cart_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        quantity: int,
        unit_price: float,
    ) -> CartItem:
        # Try to find existing item
        q = select(CartItem).where(
            CartItem.cart_id == cart_id,
            CartItem.product_id == product_id,
        )
        q = (
            q.where(CartItem.variant_id == variant_id)
            if variant_id
            else q.where(CartItem.variant_id.is_(None))
        )
        result = await db.execute(q)
        existing = result.scalar_one_or_none()

        if existing:
            existing.quantity = min(existing.quantity + quantity, 100)
            await db.flush()
            return existing

        item = CartItem(
            id=uuid.uuid4(),
            cart_id=cart_id,
            product_id=product_id,
            variant_id=variant_id,
            quantity=quantity,
            unit_price=unit_price,
        )
        db.add(item)
        await db.flush()
        await db.refresh(item)
        return item

    async def update_item_quantity(
        self, db: AsyncSession, item_id: uuid.UUID, quantity: int
    ) -> CartItem | None:
        await db.execute(
            update(CartItem).where(CartItem.id == item_id).values(quantity=quantity)
        )
        result = await db.execute(select(CartItem).where(CartItem.id == item_id))
        return result.scalar_one_or_none()

    async def remove_item(self, db: AsyncSession, item_id: uuid.UUID) -> bool:
        result = await db.execute(delete(CartItem).where(CartItem.id == item_id))
        return result.rowcount > 0

    async def clear_items(self, db: AsyncSession, cart_id: uuid.UUID) -> None:
        await db.execute(delete(CartItem).where(CartItem.cart_id == cart_id))

    async def update_cart(
        self, db: AsyncSession, cart_id: uuid.UUID, data: dict[str, Any]
    ) -> None:
        await db.execute(update(Cart).where(Cart.id == cart_id).values(**data))

    async def merge_guest_into_user(
        self, db: AsyncSession, guest_cart: Cart, user_cart: Cart
    ) -> None:
        """Move guest cart items into user cart (additive merge).

        Batches the existing-item lookup plus the resulting updates/inserts
        into a constant number of round trips instead of one upsert (a
        SELECT + INSERT-or-UPDATE) per guest item. A native
        INSERT ... ON CONFLICT DO UPDATE isn't safe here because variant_id
        is nullable and part of the unique constraint — Postgres never
        treats NULL = NULL as a conflict, so it would silently duplicate
        rows for variant-less products instead of merging quantities.
        """
        if guest_cart.items:
            product_ids = [item.product_id for item in guest_cart.items]
            existing_result = await db.execute(
                select(CartItem).where(
                    CartItem.cart_id == user_cart.id,
                    CartItem.product_id.in_(product_ids),
                )
            )
            existing_by_key = {
                (row.product_id, row.variant_id): row
                for row in existing_result.scalars().all()
            }

            to_update = []
            to_insert = []
            for item in guest_cart.items:
                existing = existing_by_key.get((item.product_id, item.variant_id))
                if existing:
                    to_update.append(
                        {
                            "item_id": existing.id,
                            "new_quantity": min(existing.quantity + item.quantity, 100),
                        }
                    )
                else:
                    to_insert.append(
                        {
                            "id": uuid.uuid4(),
                            "cart_id": user_cart.id,
                            "product_id": item.product_id,
                            "variant_id": item.variant_id,
                            "quantity": min(item.quantity, 100),
                            "unit_price": item.unit_price,
                        }
                    )

            if to_update:
                stmt = (
                    update(CartItem)
                    .where(CartItem.id == bindparam("item_id"))
                    .values(quantity=bindparam("new_quantity"))
                )
                await db.execute(stmt, to_update)

            if to_insert:
                await db.execute(insert(CartItem), to_insert)

        # Expire guest cart immediately
        await db.execute(
            update(Cart)
            .where(Cart.id == guest_cart.id)
            .values(expires_at=datetime.now(UTC))
        )
