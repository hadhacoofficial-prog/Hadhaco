from __future__ import annotations

import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.redis import get_redis
from app.modules.cms.media_service import CmsMediaService
from app.modules.cms.schemas import (
    AdminSectionOut,
    BannerCreate,
    BannerOut,
    BannerUpdate,
    CmsMediaOut,
    CmsMediaUpdate,
    CmsPageCreate,
    CmsPageOut,
    CmsPageUpdate,
    HomepageDataOut,
    LandingSectionOut,
    LandingSectionUpdate,
    MediaListOut,
    PublishLogOut,
    PublishSectionRequest,
    ReorderSectionEntry,
    SaveDraftRequest,
    SectionItemCreate,
    SectionItemOut,
    SectionItemReorderEntry,
    SectionItemUpdate,
    VersionHistoryOut,
)
from app.modules.cms.service import CMSService

router = APIRouter(prefix="/cms", tags=["cms"])
_svc = CMSService()
_media_svc = CmsMediaService()


# ── Public: legacy home ────────────────────────────────────────────────────────


@router.get("/home", response_model=BaseSuccessResponse[dict])
async def get_home(db: AsyncSession = Depends(get_db)):
    data = await _svc.get_home_data(db)
    return ok(data, ResponseCode.CMS_HOME_FETCHED, "Home page data fetched")


# ── Public: homepage (new rich endpoint) ───────────────────────────────────────


@router.get("/homepage")
async def get_homepage(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    data = await _svc.get_homepage(db, redis)
    payload = ok(
        HomepageDataOut(**data),
        ResponseCode.CMS_HOMEPAGE_FETCHED,
        "Homepage data fetched",
    )
    import json as _json

    content = _json.loads(payload.model_dump_json())
    return JSONResponse(
        content=content,
        headers={"Cache-Control": "no-store"},
    )


# ── Public: pages ─────────────────────────────────────────────────────────────


@router.get("/pages/{slug}", response_model=BaseSuccessResponse[CmsPageOut])
async def get_page(slug: str, db: AsyncSession = Depends(get_db)):
    result = await _svc.get_page(db, slug)
    return ok(result, ResponseCode.CMS_PAGE_FETCHED, "Page fetched")


# ── Admin: banners ─────────────────────────────────────────────────────────────


@router.get("/admin/banners", response_model=BaseSuccessResponse[list[BannerOut]])
async def list_banners(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await _svc.list_banners(db)
    return ok(result, ResponseCode.CMS_BANNER_LISTED, "Banners listed")


@router.post(
    "/admin/banners", response_model=BaseSuccessResponse[BannerOut], status_code=201
)
async def create_banner(
    data: BannerCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)
):
    from app.common.responses import created

    result = await _svc.create_banner(db, data)
    return created(result, ResponseCode.CMS_BANNER_CREATED, "Banner created")


@router.patch(
    "/admin/banners/{banner_id}", response_model=BaseSuccessResponse[BannerOut]
)
async def update_banner(
    banner_id: uuid.UUID,
    data: BannerUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.update_banner(db, banner_id, data)
    return ok(result, ResponseCode.CMS_BANNER_UPDATED, "Banner updated")


@router.delete("/admin/banners/{banner_id}", response_model=BaseSuccessResponse[None])
async def delete_banner(
    banner_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)
):
    await _svc.delete_banner(db, banner_id)
    return deleted(ResponseCode.CMS_BANNER_DELETED, "Banner deleted")


# ── Admin: sections list + reorder ─────────────────────────────────────────────


@router.get(
    "/admin/sections", response_model=BaseSuccessResponse[list[AdminSectionOut]]
)
async def list_sections(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    results = await _svc.list_sections_with_items(db)
    out = [
        AdminSectionOut.model_validate({**r["section"].__dict__, "items": r["items"]})
        for r in results
    ]
    return ok(out, ResponseCode.CMS_SECTION_LISTED, "Sections listed")


@router.post("/admin/sections/reorder", response_model=BaseSuccessResponse[None])
async def reorder_sections(
    entries: list[ReorderSectionEntry],
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    admin=Depends(require_admin),
):
    await _svc.reorder_sections(db, redis, entries, admin.id)
    return ok(None, ResponseCode.CMS_SECTIONS_REORDERED, "Sections reordered")


# ── Admin: single section ──────────────────────────────────────────────────────


@router.get(
    "/admin/sections/{section_key}", response_model=BaseSuccessResponse[AdminSectionOut]
)
async def get_section(
    section_key: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)
):
    result = await _svc.get_section(db, section_key)
    out = AdminSectionOut.model_validate(
        {**result["section"].__dict__, "items": result["items"]}
    )
    return ok(out, ResponseCode.CMS_SECTION_FETCHED, "Section fetched")


@router.patch(
    "/admin/sections/{section_key}",
    response_model=BaseSuccessResponse[LandingSectionOut],
)
async def update_section(
    section_key: str,
    data: LandingSectionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.update_section(db, section_key, data)
    return ok(result, ResponseCode.CMS_SECTION_UPDATED, "Section updated")


@router.patch(
    "/admin/sections/{section_key}/draft",
    response_model=BaseSuccessResponse[LandingSectionOut],
)
async def save_draft(
    section_key: str,
    data: SaveDraftRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    result = await _svc.save_draft(db, section_key, data, admin.id)
    return ok(result, ResponseCode.CMS_DRAFT_SAVED, "Draft saved")


@router.post(
    "/admin/sections/{section_key}/publish",
    response_model=BaseSuccessResponse[LandingSectionOut],
)
async def publish_section(
    section_key: str,
    data: PublishSectionRequest = PublishSectionRequest(),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    admin=Depends(require_admin),
):
    result = await _svc.publish_section(db, redis, section_key, data, admin.id)
    return ok(result, ResponseCode.CMS_SECTION_PUBLISHED, "Section published")


@router.post(
    "/admin/sections/{section_key}/toggle",
    response_model=BaseSuccessResponse[LandingSectionOut],
)
async def toggle_section(
    section_key: str,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    admin=Depends(require_admin),
):
    result = await _svc.toggle_section(db, redis, section_key, admin.id)
    return ok(result, ResponseCode.CMS_SECTION_TOGGLED, "Section toggled")


# ── Admin: version history ─────────────────────────────────────────────────────


@router.get(
    "/admin/sections/{section_key}/versions",
    response_model=BaseSuccessResponse[list[VersionHistoryOut]],
)
async def get_versions(
    section_key: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)
):
    result = await _svc.get_version_history(db, section_key)
    return ok(result, ResponseCode.CMS_VERSION_LISTED, "Versions listed")


@router.post(
    "/admin/sections/{section_key}/rollback/{version_id}",
    response_model=BaseSuccessResponse[LandingSectionOut],
)
async def rollback_version(
    section_key: str,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    admin=Depends(require_admin),
):
    result = await _svc.rollback_version(db, redis, section_key, version_id, admin.id)
    return ok(result, ResponseCode.CMS_VERSION_ROLLED_BACK, "Version rolled back")


# ── Admin: section items ───────────────────────────────────────────────────────


@router.get(
    "/admin/sections/{section_key}/items",
    response_model=BaseSuccessResponse[list[SectionItemOut]],
)
async def list_items(
    section_key: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)
):
    result = await _svc.list_items(db, section_key)
    return ok(result, ResponseCode.CMS_ITEMS_LISTED, "Items listed")


@router.post(
    "/admin/sections/{section_key}/items",
    response_model=BaseSuccessResponse[SectionItemOut],
    status_code=201,
)
async def create_item(
    section_key: str,
    data: SectionItemCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.common.responses import created

    result = await _svc.create_item(db, section_key, data)
    return created(result, ResponseCode.CMS_ITEM_CREATED, "Item created")


@router.patch(
    "/admin/sections/{section_key}/items/{item_id}",
    response_model=BaseSuccessResponse[SectionItemOut],
)
async def update_item(
    section_key: str,
    item_id: uuid.UUID,
    data: SectionItemUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.update_item(db, section_key, item_id, data)
    return ok(result, ResponseCode.CMS_ITEM_UPDATED, "Item updated")


@router.delete(
    "/admin/sections/{section_key}/items/{item_id}",
    response_model=BaseSuccessResponse[None],
)
async def delete_item(
    section_key: str,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    await _svc.delete_item(db, section_key, item_id)
    return deleted(ResponseCode.CMS_ITEM_DELETED, "Item deleted")


@router.post(
    "/admin/sections/{section_key}/items/reorder",
    response_model=BaseSuccessResponse[None],
)
async def reorder_items(
    section_key: str,
    entries: list[SectionItemReorderEntry],
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    await _svc.reorder_items(db, section_key, entries)
    return ok(None, ResponseCode.CMS_ITEMS_REORDERED, "Items reordered")


# ── Admin: media library ───────────────────────────────────────────────────────


@router.get("/admin/media", response_model=BaseSuccessResponse[MediaListOut])
async def list_media(
    folder: str | None = Query(None),
    mime_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(48, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    items, total = await _svc.list_media(db, folder, mime_type, page, page_size)
    import math

    out = MediaListOut(
        items=[CmsMediaOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )
    return ok(out, ResponseCode.CMS_MEDIA_LISTED, "Media listed")


@router.post(
    "/admin/media/upload",
    response_model=BaseSuccessResponse[CmsMediaOut],
    status_code=201,
)
async def upload_media(
    file: Annotated[UploadFile, File()],
    folder: str = Form("/"),
    alt_text: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    from app.common.responses import created

    result = await _media_svc.upload(db, file, folder, alt_text, admin.id)
    return created(result, ResponseCode.CMS_MEDIA_UPLOADED, "Media uploaded")


@router.patch(
    "/admin/media/{media_id}", response_model=BaseSuccessResponse[CmsMediaOut]
)
async def update_media(
    media_id: uuid.UUID,
    data: CmsMediaUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.update_media(db, media_id, data)
    return ok(result, ResponseCode.CMS_MEDIA_UPDATED, "Media updated")


@router.delete("/admin/media/{media_id}", response_model=BaseSuccessResponse[None])
async def delete_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    await _svc.delete_media(db, media_id)
    return deleted(ResponseCode.CMS_MEDIA_DELETED, "Media deleted")


# ── Admin: cache + logs ────────────────────────────────────────────────────────


@router.post("/admin/cache/invalidate", response_model=BaseSuccessResponse[None])
async def invalidate_cache(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    admin=Depends(require_admin),
):
    await _svc.invalidate_homepage_cache(db, redis, admin.id)
    await db.commit()
    return ok(None, ResponseCode.CMS_CACHE_INVALIDATED, "Cache invalidated")


@router.get(
    "/admin/publish-log", response_model=BaseSuccessResponse[list[PublishLogOut]]
)
async def get_publish_log(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.get_publish_log(db, limit)
    return ok(result, ResponseCode.CMS_PUBLISH_LOG_LISTED, "Publish log fetched")


# ── Admin: pages ───────────────────────────────────────────────────────────────


@router.post(
    "/admin/pages", response_model=BaseSuccessResponse[CmsPageOut], status_code=201
)
async def create_page(
    data: CmsPageCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)
):
    from app.common.responses import created

    result = await _svc.create_page(db, data)
    return created(result, ResponseCode.CMS_PAGE_CREATED, "Page created")


@router.patch("/admin/pages/{page_id}", response_model=BaseSuccessResponse[CmsPageOut])
async def update_page(
    page_id: uuid.UUID,
    data: CmsPageUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.update_page(db, page_id, data)
    return ok(result, ResponseCode.CMS_PAGE_UPDATED, "Page updated")
