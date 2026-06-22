import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.modules.inventory.schemas import (
    InventoryMovementListResponse,
    InventoryMovementResponse,
    LowStockItem,
    ManualAdjustmentRequest,
)
from app.modules.inventory.service import InventoryService
from app.modules.profiles.models import Profile

router = APIRouter()
_service = InventoryService()


@router.get(
    "/admin/inventory/low-stock",
    response_model=BaseSuccessResponse[list[LowStockItem]],
    dependencies=[Depends(require_admin)],
)
async def get_low_stock(db: AsyncSession = Depends(get_db)):
    result = await _service.get_low_stock(db)
    return ok(
        result,
        ResponseCode.INVENTORY_LOW_STOCK_LISTED,
        "Low stock items listed successfully",
    )


@router.get(
    "/admin/products/{product_id}/inventory",
    response_model=BaseSuccessResponse[InventoryMovementListResponse],
    dependencies=[Depends(require_admin)],
)
async def get_inventory_history(
    product_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    movement_type: str | None = Query(
        None,
        pattern="^(purchase|sale|return|adjustment|damage|transfer|correction)$",
    ),
    db: AsyncSession = Depends(get_db),
):
    result = await _service.get_history(
        db,
        product_id,
        page=page,
        page_size=page_size,
        movement_type=movement_type,
    )
    return ok(
        result,
        ResponseCode.INVENTORY_HISTORY_FETCHED,
        "Inventory history fetched successfully",
    )


@router.post(
    "/admin/products/{product_id}/inventory/adjust",
    response_model=BaseSuccessResponse[InventoryMovementResponse],
    dependencies=[Depends(require_admin)],
)
async def manual_adjustment(
    product_id: uuid.UUID,
    payload: ManualAdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.manual_adjustment(db, product_id, payload, current_user.id)
    return ok(
        result, ResponseCode.INVENTORY_ADJUSTED, "Inventory adjusted successfully"
    )
