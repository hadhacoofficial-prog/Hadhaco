import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.collections.schemas import (
    AddProductsToCollectionRequest,
    CollectionCreateRequest,
    CollectionResponse,
    CollectionUpdateRequest,
)
from app.modules.collections.service import CollectionService

router = APIRouter()
_service = CollectionService()


@router.get(
    "/admin/collections",
    response_model=BaseSuccessResponse[list[CollectionResponse]],
    dependencies=[Depends(require_admin)],
)
async def admin_list_collections(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select as sa_select

    from app.modules.collections.models import Collection

    result = await db.execute(
        sa_select(Collection)
        .where(Collection.deleted_at.is_(None))
        .order_by(Collection.sort_order.asc(), Collection.name.asc())
    )
    cols = list(result.scalars().all())
    return ok(
        [CollectionResponse.model_validate(c) for c in cols],
        ResponseCode.COLLECTION_LISTED,
        "All collections listed",
    )


@router.get(
    "/collections", response_model=BaseSuccessResponse[list[CollectionResponse]]
)
async def list_collections(db: AsyncSession = Depends(get_db)):
    result = await _service.list_active(db)
    return ok(result, ResponseCode.COLLECTION_LISTED, "Collections listed successfully")


@router.get(
    "/collections/{slug}", response_model=BaseSuccessResponse[CollectionResponse]
)
async def get_collection(slug: str, db: AsyncSession = Depends(get_db)):
    result = await _service.get_by_slug(db, slug)
    return ok(
        result, ResponseCode.COLLECTION_FETCHED, "Collection fetched successfully"
    )


@router.post(
    "/admin/collections",
    response_model=BaseSuccessResponse[CollectionResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_collection(
    payload: CollectionCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.common.responses import created

    result = await _service.create(db, payload)
    return created(
        result, ResponseCode.COLLECTION_CREATED, "Collection created successfully"
    )


@router.patch(
    "/admin/collections/{col_id}",
    response_model=BaseSuccessResponse[CollectionResponse],
    dependencies=[Depends(require_admin)],
)
async def update_collection(
    col_id: uuid.UUID,
    payload: CollectionUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.update(db, col_id, payload)
    return ok(
        result, ResponseCode.COLLECTION_UPDATED, "Collection updated successfully"
    )


@router.delete(
    "/admin/collections/{col_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_collection(
    col_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _service.delete(db, col_id)
    return deleted(ResponseCode.COLLECTION_DELETED, "Collection deleted successfully")


@router.post(
    "/admin/collections/{col_id}/products",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def add_products_to_collection(
    col_id: uuid.UUID,
    payload: AddProductsToCollectionRequest,
    db: AsyncSession = Depends(get_db),
):
    await _service.add_products(db, col_id, payload)
    return ok(
        None, ResponseCode.COLLECTION_PRODUCTS_ADDED, "Products added to collection"
    )


@router.delete(
    "/admin/collections/{col_id}/products/{product_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def remove_product_from_collection(
    col_id: uuid.UUID,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _service.remove_product(db, col_id, product_id)
    return deleted(
        ResponseCode.COLLECTION_PRODUCT_REMOVED, "Product removed from collection"
    )
