import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.cart.models import Cart, CartItem
from app.modules.cart.repository import CartRepository
from app.modules.cart.schemas import (
    AddToCartRequest,
    ApplyCouponRequest,
    CartItemResponse,
    CartSummary,
    UpdateCartItemRequest,
)

_repo = CartRepository()

_DEFAULT_TAX_RATE = 0.03  # 3% GST fallback; per-item rates used at order creation


def _build_summary(cart: Cart) -> CartSummary:
    items = [CartItemResponse.from_orm_with_total(i) for i in cart.items]
    subtotal = round(sum(i.line_total for i in items), 2)
    tax = round(subtotal * _DEFAULT_TAX_RATE, 2)
    discount = float(cart.discount)
    total = round(max(subtotal + tax - discount, 0), 2)
    return CartSummary(
        id=cart.id,
        items=items,
        item_count=sum(i.quantity for i in items),
        subtotal=subtotal,
        tax_amount=tax,
        discount=discount,
        total=total,
        coupon_code=cart.coupon_code,
        expires_at=cart.expires_at,
    )


class CartService:

    async def _get_or_create(
        self,
        db: AsyncSession,
        user_id: uuid.UUID | None,
        session_id: str | None,
    ) -> Cart:
        if user_id:
            cart = await _repo.get_for_user(db, user_id)
            if not cart:
                cart = await _repo.create(db, user_id, None)
        elif session_id:
            cart = await _repo.get_by_session(db, session_id)
            if not cart:
                cart = await _repo.create(db, None, session_id)
        else:
            raise ValidationError("Either user_id or session_id is required")
        return cart

    async def _fetch_product_price(self, db: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID | None) -> float:
        if variant_id:
            row = await db.execute(
                text(
                    "SELECT p.base_price + COALESCE(v.price_adjustment, 0) AS price "
                    "FROM products p "
                    "JOIN product_variants v ON v.id = :vid "
                    "WHERE p.id = :pid AND p.deleted_at IS NULL AND p.status = 'active'"
                ),
                {"pid": str(product_id), "vid": str(variant_id)},
            )
        else:
            row = await db.execute(
                text(
                    "SELECT base_price AS price FROM products "
                    "WHERE id = :pid AND deleted_at IS NULL AND status = 'active'"
                ),
                {"pid": str(product_id)},
            )
        result = row.fetchone()
        if not result:
            raise NotFoundError("Product not found or unavailable")
        return float(result[0])

    async def get_cart(
        self,
        db: AsyncSession,
        user_id: uuid.UUID | None = None,
        session_id: str | None = None,
    ) -> CartSummary:
        cart = await self._get_or_create(db, user_id, session_id)
        return _build_summary(cart)

    async def add_item(
        self,
        db: AsyncSession,
        payload: AddToCartRequest,
        user_id: uuid.UUID | None = None,
        session_id: str | None = None,
    ) -> CartSummary:
        cart = await self._get_or_create(db, user_id, session_id)
        unit_price = await self._fetch_product_price(db, payload.product_id, payload.variant_id)
        await _repo.upsert_item(db, cart.id, payload.product_id, payload.variant_id, payload.quantity, unit_price)
        # Reload with fresh items
        cart = await _repo.get_by_id(db, cart.id)
        return _build_summary(cart)

    async def update_item(
        self,
        db: AsyncSession,
        cart_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: UpdateCartItemRequest,
        user_id: uuid.UUID | None = None,
    ) -> CartSummary:
        cart = await _repo.get_by_id(db, cart_id)
        if not cart:
            raise NotFoundError("Cart not found")
        if user_id and cart.user_id != user_id:
            raise NotFoundError("Cart not found")

        item = next((i for i in cart.items if i.id == item_id), None)
        if not item:
            raise NotFoundError("Cart item not found")

        await _repo.update_item_quantity(db, item_id, payload.quantity)
        cart = await _repo.get_by_id(db, cart_id)
        return _build_summary(cart)

    async def remove_item(
        self,
        db: AsyncSession,
        cart_id: uuid.UUID,
        item_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> CartSummary:
        cart = await _repo.get_by_id(db, cart_id)
        if not cart:
            raise NotFoundError("Cart not found")
        if user_id and cart.user_id != user_id:
            raise NotFoundError("Cart not found")

        await _repo.remove_item(db, item_id)
        cart = await _repo.get_by_id(db, cart_id)
        return _build_summary(cart)

    async def clear(
        self,
        db: AsyncSession,
        user_id: uuid.UUID | None = None,
        session_id: str | None = None,
    ) -> CartSummary:
        cart = await self._get_or_create(db, user_id, session_id)
        await _repo.clear_items(db, cart.id)
        await _repo.update_cart(db, cart.id, {"coupon_code": None, "discount": 0})
        cart = await _repo.get_by_id(db, cart.id)
        return _build_summary(cart)

    async def merge_guest_cart(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: str,
    ) -> CartSummary:
        """Called on login: merge guest session cart into user cart."""
        guest_cart = await _repo.get_by_session(db, session_id)
        if not guest_cart or not guest_cart.items:
            return await self.get_cart(db, user_id=user_id)

        user_cart = await _repo.get_for_user(db, user_id)
        if not user_cart:
            user_cart = await _repo.create(db, user_id, None)
            # reload with items
            user_cart = await _repo.get_by_id(db, user_cart.id)

        await _repo.merge_guest_into_user(db, guest_cart, user_cart)
        user_cart = await _repo.get_by_id(db, user_cart.id)
        return _build_summary(user_cart)
