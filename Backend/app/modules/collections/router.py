import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.collections.schemas import (
    AddProductsToCollectionRequest,
    BulkActionRequest,
    CollectionCreateRequest,
    CollectionDetailResponse,
    CollectionListResponse,
    CollectionProductItem,
    CollectionResponse,
    ReorderProductsRequest,
    CollectionUpdateRequest,
)
from app.modules.collections.service import CollectionService

router = APIRouter()
_service = CollectionService()


# ── Public ──────────────────────────────────────────────────────────────────


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


# ── Admin ────────────────────────────────────────────────────────────────────


@router.get(
    "/admin/collections",
    response_model=BaseSuccessResponse[CollectionListResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_list_collections(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = Query(None, max_length=200),
    is_active: bool | None = None,
    is_featured: bool | None = None,
    sort_by: str = Query("sort_order", pattern="^(sort_order|name|updated_at|created_at)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    result = await _service.list_admin(
        db,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        is_featured=is_featured,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return ok(result, ResponseCode.COLLECTION_LISTED, "Collections listed successfully")


@router.get(
    "/admin/collections/{col_id}",
    response_model=BaseSuccessResponse[CollectionDetailResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_get_collection(
    col_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await _service.get_detail(db, col_id)
    return ok(result, ResponseCode.COLLECTION_FETCHED, "Collection fetched successfully")


@router.post(
    "/admin/collections",
    response_model=BaseSuccessResponse[CollectionDetailResponse],
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
    response_model=BaseSuccessResponse[CollectionDetailResponse],
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
    "/admin/collections/bulk",
    response_model=BaseSuccessResponse[None],
    dependencies=[Depends(require_admin)],
)
async def bulk_action_collections(
    payload: BulkActionRequest,
    db: AsyncSession = Depends(get_db),
):
    await _service.bulk_action(db, payload)
    return ok(None, ResponseCode.COLLECTION_UPDATED, "Bulk action applied")


@router.get(
    "/admin/collections/{col_id}/products",
    response_model=BaseSuccessResponse[dict],
    dependencies=[Depends(require_admin)],
)
async def admin_get_collection_products(
    col_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = await _service.get_products(db, col_id, page=page, page_size=page_size)
    return ok(
        {
            "items": [i.model_dump() for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
        ResponseCode.PRODUCT_LISTED,
        "Collection products listed",
    )


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


@router.patch(
    "/admin/collections/{col_id}/products/reorder",
    response_model=BaseSuccessResponse[None],
    dependencies=[Depends(require_admin)],
)
async def reorder_collection_products(
    col_id: uuid.UUID,
    payload: ReorderProductsRequest,
    db: AsyncSession = Depends(get_db),
):
    await _service.reorder_products(db, col_id, payload)
    return ok(None, ResponseCode.COLLECTION_UPDATED, "Products reordered")
