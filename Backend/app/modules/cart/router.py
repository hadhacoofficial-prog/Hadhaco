import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user_optional
from app.modules.cart.schemas import (
    AddToCartRequest,
    CartSummary,
    UpdateCartItemRequest,
)
from app.modules.cart.service import CartService

router = APIRouter()
_service = CartService()


def _resolve_identity(
    current_user=None,
    x_session_id: str | None = None,
) -> tuple[uuid.UUID | None, str | None]:
    user_id = current_user.id if current_user else None
    session_id = None if user_id else x_session_id
    return user_id, session_id


@router.get("/cart", response_model=BaseSuccessResponse[CartSummary])
async def get_cart(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    user_id, session_id = _resolve_identity(current_user, x_session_id)
    result = await _service.get_cart(db, user_id=user_id, session_id=session_id)
    return ok(result, ResponseCode.CART_FETCHED, "Cart fetched successfully")


@router.post("/cart/items", response_model=BaseSuccessResponse[CartSummary])
async def add_to_cart(
    payload: AddToCartRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    user_id, session_id = _resolve_identity(current_user, x_session_id)
    result = await _service.add_item(
        db, payload, user_id=user_id, session_id=session_id
    )
    return ok(result, ResponseCode.CART_ITEM_ADDED, "Item added to cart")


@router.patch(
    "/cart/{cart_id}/items/{item_id}", response_model=BaseSuccessResponse[CartSummary]
)
async def update_cart_item(
    cart_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: UpdateCartItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    user_id = current_user.id if current_user else None
    result = await _service.update_item(db, cart_id, item_id, payload, user_id=user_id)
    return ok(result, ResponseCode.CART_ITEM_UPDATED, "Cart item updated")


@router.delete(
    "/cart/{cart_id}/items/{item_id}", response_model=BaseSuccessResponse[CartSummary]
)
async def remove_cart_item(
    cart_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    user_id = current_user.id if current_user else None
    result = await _service.remove_item(db, cart_id, item_id, user_id=user_id)
    return ok(result, ResponseCode.CART_ITEM_REMOVED, "Item removed from cart")


@router.delete("/cart", response_model=BaseSuccessResponse[CartSummary])
async def clear_cart(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    user_id, session_id = _resolve_identity(current_user, x_session_id)
    result = await _service.clear(db, user_id=user_id, session_id=session_id)
    return ok(result, ResponseCode.CART_CLEARED, "Cart cleared successfully")


@router.post("/cart/merge", response_model=BaseSuccessResponse[CartSummary])
async def merge_guest_cart(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    """Call after login to merge guest cart into authenticated user cart."""
    from app.core.exceptions import AuthenticationError

    if not current_user:
        raise AuthenticationError("Authentication required to merge cart")
    if not x_session_id:
        from app.core.exceptions import ValidationError

        raise ValidationError("X-Session-ID header required")
    result = await _service.merge_guest_cart(db, current_user.id, x_session_id)
    return ok(result, ResponseCode.CART_MERGED, "Cart merged successfully")
