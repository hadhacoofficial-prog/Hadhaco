import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user_optional
from app.modules.search.service import SearchService

router = APIRouter()
_service = SearchService()


@router.get("/search", response_model=BaseSuccessResponse[dict])
async def search_products(
    q: str = Query(..., min_length=1, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: uuid.UUID | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    result = await _service.full_text_search(
        db,
        q,
        page=page,
        page_size=page_size,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
    )
    # Record search async (fire-and-forget pattern — swallow errors)
    try:
        user_id = str(current_user.id) if current_user else None
        await _service.record_search(db, q, user_id, result["total"])
    except Exception:
        pass
    return ok(
        result,
        ResponseCode.SEARCH_RESULTS_FETCHED,
        "Search results fetched successfully",
    )


@router.get("/search/autocomplete", response_model=BaseSuccessResponse[dict])
async def autocomplete(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    suggestions = await _service.autocomplete(db, q, limit)
    return ok(
        {"suggestions": suggestions},
        ResponseCode.SEARCH_AUTOCOMPLETE_FETCHED,
        "Autocomplete suggestions fetched",
    )


@router.get("/search/trending", response_model=BaseSuccessResponse)
async def trending_searches(
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    result = await _service.trending_searches(db, limit)
    return ok(
        result,
        ResponseCode.SEARCH_TRENDING_FETCHED,
        "Trending searches fetched successfully",
    )
