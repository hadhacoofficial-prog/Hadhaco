import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_customer
from app.modules.profiles.models import Profile
from app.modules.wishlist.schemas import AddToWishlistRequest, WishlistResponse
from app.modules.wishlist.service import WishlistService

router = APIRouter()
_service = WishlistService()


@router.get(
    "/me/wishlist",
    response_model=BaseSuccessResponse[WishlistResponse],
    dependencies=[Depends(require_customer)],
)
async def get_wishlist(
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.get(db, current_user.id)
    return ok(result, ResponseCode.WISHLIST_FETCHED, "Wishlist fetched successfully")


@router.post(
    "/me/wishlist",
    response_model=BaseSuccessResponse[WishlistResponse],
    dependencies=[Depends(require_customer)],
)
async def add_to_wishlist(
    payload: AddToWishlistRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.add(db, current_user.id, payload)
    return ok(result, ResponseCode.WISHLIST_ITEM_ADDED, "Item added to wishlist")


@router.post(
    "/me/wishlist/toggle",
    response_model=BaseSuccessResponse[WishlistResponse],
    dependencies=[Depends(require_customer)],
)
async def toggle_wishlist(
    payload: AddToWishlistRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.toggle(db, current_user.id, payload)
    return ok(result, ResponseCode.WISHLIST_TOGGLED, "Wishlist toggled successfully")


@router.delete(
    "/me/wishlist/{product_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_customer)],
)
async def remove_from_wishlist(
    product_id: uuid.UUID,
    variant_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    await _service.remove(db, current_user.id, product_id, variant_id)
    return deleted(ResponseCode.WISHLIST_ITEM_REMOVED, "Item removed from wishlist")
