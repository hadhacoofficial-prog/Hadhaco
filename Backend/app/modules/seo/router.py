import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.cache import (
    PREFIX_SEO_PAGE,
    PREFIX_SITEMAP,
    TTL_SEO_PAGE,
    TTL_SITEMAP,
    add_cache_headers,
    bust_seo_page_cache,
    check_not_modified,
    make_etag,
    not_modified_response,
)
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.redis import get_redis, safe_redis_get, safe_redis_setex
from app.modules.seo.service import SeoService

router = APIRouter()
_service = SeoService()


class SeoPageUpsertRequest(BaseModel):
    path: str
    title: str | None = None
    description: str | None = None
    canonical_url: str | None = None
    og_image: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    structured_data: str | None = None
    noindex: bool = False


class SeoRedirectRequest(BaseModel):
    from_path: str
    to_path: str
    status_code: int = 301


@router.get("/seo/page", response_model=BaseSuccessResponse[dict])
async def get_seo_page(
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = f"{PREFIX_SEO_PAGE}:{path}"
    cached = await safe_redis_get(redis, cache_key)
    if cached:
        etag = make_etag(cached)
        if check_not_modified(request, etag):
            return not_modified_response()
        import json as _json

        from fastapi.responses import JSONResponse

        content = _json.loads(cached)
        response = JSONResponse(content=content)
        add_cache_headers(response, TTL_SEO_PAGE, etag=etag)
        return response

    data = await _service.get_page(db, path)
    if not data:
        raise HTTPException(status_code=404, detail="SEO page not found")
    import json as _json

    from fastapi.responses import JSONResponse

    response_data = ok(
        data, ResponseCode.SEO_PAGE_FETCHED, "SEO page fetched successfully"
    )
    serialized = _json.dumps(_json.loads(response_data.model_dump_json()), default=str)
    await safe_redis_setex(redis, cache_key, TTL_SEO_PAGE, serialized)
    etag = make_etag(serialized)
    content = _json.loads(serialized)
    response = JSONResponse(content=content)
    add_cache_headers(response, TTL_SEO_PAGE, etag=etag)
    return response


@router.put(
    "/admin/seo/pages",
    response_model=BaseSuccessResponse[dict],
    dependencies=[Depends(require_admin)],
)
async def upsert_seo_page(
    payload: SeoPageUpsertRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.upsert_page(db, payload.model_dump())
    from app.core.redis import get_redis_pool

    redis = get_redis_pool()
    await bust_seo_page_cache(redis, payload.path)
    return ok(result, ResponseCode.SEO_PAGE_UPSERTED, "SEO page upserted successfully")


@router.post(
    "/admin/seo/redirects",
    response_model=BaseSuccessResponse[None],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_redirect(
    payload: SeoRedirectRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.common.responses import created

    await _service.create_redirect(
        db, payload.from_path, payload.to_path, payload.status_code
    )
    return created(
        None, ResponseCode.SEO_REDIRECT_CREATED, "Redirect created successfully"
    )


@router.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = PREFIX_SITEMAP
    cached = await safe_redis_get(redis, cache_key)
    if cached:
        etag = make_etag(cached)
        if check_not_modified(request, etag):
            from fastapi.responses import Response as _Resp

            return _Resp(status_code=304)
        from fastapi.responses import PlainTextResponse as _PTR

        response = _PTR(content=cached, media_type="application/xml")
        add_cache_headers(response, TTL_SITEMAP, etag=etag, immutable=True)
        return response

    xml = await _service.generate_sitemap(db)
    await safe_redis_setex(redis, cache_key, TTL_SITEMAP, xml)
    etag = make_etag(xml)
    from fastapi.responses import PlainTextResponse as _PTR

    response = _PTR(content=xml, media_type="application/xml")
    add_cache_headers(response, TTL_SITEMAP, etag=etag, immutable=True)
    return response
