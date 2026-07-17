import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.cache import (
    PREFIX_AUTOCOMPLETE,
    PREFIX_SEARCH,
    PREFIX_TRENDING,
    TTL_AUTOCOMPLETE,
    TTL_SEARCH_RESULTS,
    TTL_TRENDING,
    add_cache_headers,
    check_not_modified,
    make_cache_key,
    make_etag,
    not_modified_response,
)
from app.core.database import get_db
from app.core.dependencies import get_current_user_optional
from app.core.redis import get_redis, safe_redis_get, safe_redis_setex
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
    redis: aioredis.Redis = Depends(get_redis),
    current_user=Depends(get_current_user_optional),
):
    cache_key = make_cache_key(
        PREFIX_SEARCH,
        q=q,
        page=page,
        page_size=page_size,
        category_id=str(category_id) if category_id else None,
        min_price=min_price,
        max_price=max_price,
    )
    cached = await safe_redis_get(redis, cache_key)
    if cached:
        import json as _json

        from fastapi.responses import JSONResponse

        content = _json.loads(cached)
        response = JSONResponse(content=content)
        add_cache_headers(response, TTL_SEARCH_RESULTS)
        return response

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

    response_data = ok(
        result,
        ResponseCode.SEARCH_RESULTS_FETCHED,
        "Search results fetched successfully",
    )
    import json as _json

    from fastapi.responses import JSONResponse

    serialized = _json.dumps(_json.loads(response_data.model_dump_json()), default=str)
    await safe_redis_setex(redis, cache_key, TTL_SEARCH_RESULTS, serialized)
    content = _json.loads(serialized)
    response = JSONResponse(content=content)
    add_cache_headers(response, TTL_SEARCH_RESULTS)
    return response


@router.get("/search/autocomplete", response_model=BaseSuccessResponse[dict])
async def autocomplete(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = make_cache_key(PREFIX_AUTOCOMPLETE, q=q, limit=limit)
    cached = await safe_redis_get(redis, cache_key)
    if cached:
        import json as _json

        from fastapi.responses import JSONResponse

        content = _json.loads(cached)
        response = JSONResponse(content=content)
        add_cache_headers(response, TTL_AUTOCOMPLETE)
        return response

    suggestions = await _service.autocomplete(db, q, limit)
    response_data = ok(
        {"suggestions": suggestions},
        ResponseCode.SEARCH_AUTOCOMPLETE_FETCHED,
        "Autocomplete suggestions fetched",
    )
    import json as _json

    from fastapi.responses import JSONResponse

    serialized = _json.dumps(_json.loads(response_data.model_dump_json()), default=str)
    await safe_redis_setex(redis, cache_key, TTL_AUTOCOMPLETE, serialized)
    content = _json.loads(serialized)
    response = JSONResponse(content=content)
    add_cache_headers(response, TTL_AUTOCOMPLETE)
    return response


@router.get("/search/trending", response_model=BaseSuccessResponse)
async def trending_searches(
    request: Request,
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = PREFIX_TRENDING
    cached = await safe_redis_get(redis, cache_key)
    if cached:
        etag = make_etag(cached)
        if check_not_modified(request, etag):
            return not_modified_response()

        import json as _json

        from fastapi.responses import JSONResponse

        content = _json.loads(cached)
        response = JSONResponse(content=content)
        add_cache_headers(response, TTL_TRENDING, etag=etag)
        return response

    result = await _service.trending_searches(db, limit)
    response_data = ok(
        result,
        ResponseCode.SEARCH_TRENDING_FETCHED,
        "Trending searches fetched successfully",
    )
    import json as _json

    from fastapi.responses import JSONResponse

    serialized = _json.dumps(_json.loads(response_data.model_dump_json()), default=str)
    await safe_redis_setex(redis, cache_key, TTL_TRENDING, serialized)
    etag = make_etag(serialized)
    content = _json.loads(serialized)
    response = JSONResponse(content=content)
    add_cache_headers(response, TTL_TRENDING, etag=etag)
    return response
