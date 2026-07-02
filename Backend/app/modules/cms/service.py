from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import safe_redis_delete, safe_redis_get, safe_redis_setex
from app.modules.cms.models import Banner, CmsMedia, CmsPage, LandingSection
from app.modules.cms.repository import CMSRepository
from app.modules.cms.schemas import (
    BannerCreate,
    BannerUpdate,
    CmsMediaUpdate,
    CmsPageCreate,
    CmsPageUpdate,
    LandingSectionUpdate,
    PublishSectionRequest,
    ReorderSectionEntry,
    SaveDraftRequest,
    SectionItemCreate,
    SectionItemReorderEntry,
    SectionItemUpdate,
)

_HOMEPAGE_CACHE_KEY = "cms:homepage"
_HOMEPAGE_CACHE_TTL = 86_400  # 24 h

# Sections that are still fully hardcoded on the storefront and never read CMS
# data — hidden from the admin CMS so editing them can't create a false
# impression that they affect the site.
_UNMANAGED_SECTION_KEYS = frozenset({"navbar", "shop_by_gender", "shop_by_category"})


class CMSService:
    def __init__(self) -> None:
        self._repo = CMSRepository()

    # ── Public homepage ────────────────────────────────────────────────────────

    async def get_home_data(self, db: AsyncSession) -> dict:
        """Legacy endpoint data — kept for backward compat."""
        heroes = await self._repo.get_active_banners(db, "hero")
        promo = await self._repo.get_active_banners(db, "promo_strip")
        sections = await self._repo.get_active_sections(db)
        return {
            "hero_banners": heroes,
            "promo_strip": promo[0] if promo else None,
            "sections": sections,
        }

    async def get_homepage(self, db: AsyncSession, redis: aioredis.Redis) -> dict:
        """Cache-aside: try Redis first, fall back to DB and repopulate."""
        raw = await safe_redis_get(redis, _HOMEPAGE_CACHE_KEY)
        if raw:
            return json.loads(raw)

        data = await self._build_homepage(db)
        await safe_redis_setex(
            redis,
            _HOMEPAGE_CACHE_KEY,
            _HOMEPAGE_CACHE_TTL,
            json.dumps(data, default=str),
        )
        return data

    async def _build_homepage(self, db: AsyncSession) -> dict:
        sections = await self._repo.get_active_sections(db)
        layout: list[dict] = []
        sections_map: dict[str, dict] = {}
        for s in sections:
            layout.append(
                {
                    "section_key": s.section_key,
                    "section_type": s.section_type,
                    "sort_order": s.sort_order,
                    "is_active": s.is_active,
                    "title": s.title,
                }
            )
            items = await self._repo.get_items_for_section(db, s.id)
            sections_map[s.section_key] = {
                "config": s.config,
                "items": [
                    {
                        "id": str(item.id),
                        "section_id": str(item.section_id),
                        "sort_order": item.sort_order,
                        "is_enabled": item.is_enabled,
                        "config": item.config,
                        "created_at": item.created_at.isoformat(),
                        "updated_at": item.updated_at.isoformat(),
                    }
                    for item in items
                    if item.is_enabled
                ],
            }
        return {"cache_version": 1, "layout": layout, "sections": sections_map}

    async def invalidate_homepage_cache(
        self, db: AsyncSession, redis: aioredis.Redis, admin_id: uuid.UUID | None = None
    ) -> None:
        await safe_redis_delete(redis, _HOMEPAGE_CACHE_KEY)
        await self._repo.create_publish_log(db, "cache_invalidated", None, admin_id, {})

    # ── Admin sections ─────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_manageable(key: str) -> None:
        if key in _UNMANAGED_SECTION_KEYS:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")

    async def list_sections(self, db: AsyncSession) -> list[LandingSection]:
        return await self._repo.get_all_sections(db)

    async def list_sections_with_items(self, db: AsyncSession) -> list[dict]:
        sections = await self._repo.get_all_sections(db)
        result = []
        for s in sections:
            if s.section_key in _UNMANAGED_SECTION_KEYS:
                continue
            items = await self._repo.get_items_for_section(db, s.id)
            result.append({"section": s, "items": items})
        return result

    async def get_section(self, db: AsyncSession, key: str) -> dict:
        self._ensure_manageable(key)
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        items = await self._repo.get_items_for_section(db, s.id)
        return {"section": s, "items": items}

    async def update_section(
        self, db: AsyncSession, key: str, data: LandingSectionUpdate
    ) -> LandingSection:
        self._ensure_manageable(key)
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        s = await self._repo.update_section(db, s, data.model_dump(exclude_unset=True))
        await db.commit()
        await db.refresh(s)
        return s

    async def save_draft(
        self,
        db: AsyncSession,
        key: str,
        data: SaveDraftRequest,
        admin_id: uuid.UUID,
    ) -> LandingSection:
        self._ensure_manageable(key)
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        updates: dict = {"draft_config": data.draft_config}
        if s.status == "published":
            updates["status"] = "draft"
        s = await self._repo.update_section(db, s, updates)
        await db.commit()
        await db.refresh(s)
        return s

    async def publish_section(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        key: str,
        data: PublishSectionRequest,
        admin_id: uuid.UUID,
    ) -> LandingSection:
        self._ensure_manageable(key)
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")

        if data.scheduled_at:
            updates = {"scheduled_at": data.scheduled_at, "status": "scheduled"}
            s = await self._repo.update_section(db, s, updates)
            await db.commit()
            await db.refresh(s)
            return s

        # Snapshot items
        items = await self._repo.get_items_for_section(db, s.id)
        items_snapshot = [
            {
                "id": str(i.id),
                "sort_order": i.sort_order,
                "is_enabled": i.is_enabled,
                "config": i.config,
            }
            for i in items
        ]

        new_version = s.version_number + 1
        await self._repo.create_version(
            db,
            section_id=s.id,
            version_number=new_version,
            config_snapshot=s.draft_config or s.config,
            items_snapshot=items_snapshot,
            published_by=admin_id,
            change_summary=data.change_summary,
        )

        updates = {
            "config": s.draft_config or s.config,
            "status": "published",
            "published_at": datetime.now(UTC),
            "published_by": admin_id,
            "version_number": new_version,
            "scheduled_at": None,
        }
        s = await self._repo.update_section(db, s, updates)
        await self._repo.create_publish_log(
            db, "published", key, admin_id, {"version": new_version}
        )
        await safe_redis_delete(redis, _HOMEPAGE_CACHE_KEY)
        await db.commit()
        await db.refresh(s)
        return s

    async def toggle_section(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        key: str,
        admin_id: uuid.UUID,
    ) -> LandingSection:
        self._ensure_manageable(key)
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        s = await self._repo.update_section(db, s, {"is_active": not s.is_active})
        await self._repo.create_publish_log(
            db, "toggled", key, admin_id, {"is_active": s.is_active}
        )
        await safe_redis_delete(redis, _HOMEPAGE_CACHE_KEY)
        await db.commit()
        await db.refresh(s)
        return s

    async def reorder_sections(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        entries: list[ReorderSectionEntry],
        admin_id: uuid.UUID,
    ) -> None:
        await self._repo.reorder_sections(
            db, [{"id": e.id, "sort_order": e.sort_order} for e in entries]
        )
        await self._repo.create_publish_log(
            db, "reordered", None, admin_id, {"count": len(entries)}
        )
        await safe_redis_delete(redis, _HOMEPAGE_CACHE_KEY)
        await db.commit()

    # ── Version history ────────────────────────────────────────────────────────

    async def get_version_history(self, db: AsyncSession, key: str) -> list:
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        return await self._repo.get_versions(db, s.id)

    async def rollback_version(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        key: str,
        version_id: uuid.UUID,
        admin_id: uuid.UUID,
    ) -> LandingSection:
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        v = await self._repo.get_version(db, version_id)
        if not v or v.section_id != s.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")

        new_version = s.version_number + 1
        await self._repo.create_version(
            db,
            section_id=s.id,
            version_number=new_version,
            config_snapshot=v.config_snapshot,
            items_snapshot=v.items_snapshot,
            published_by=admin_id,
            change_summary=f"Rolled back to version {v.version_number}",
        )
        updates = {
            "config": v.config_snapshot,
            "draft_config": v.config_snapshot,
            "status": "published",
            "published_at": datetime.now(UTC),
            "published_by": admin_id,
            "version_number": new_version,
        }
        s = await self._repo.update_section(db, s, updates)
        await self._repo.create_publish_log(
            db, "rolled_back", key, admin_id, {"from_version": v.version_number}
        )
        await safe_redis_delete(redis, _HOMEPAGE_CACHE_KEY)
        await db.commit()
        await db.refresh(s)
        return s

    # ── Section items ──────────────────────────────────────────────────────────

    async def list_items(self, db: AsyncSession, key: str) -> list:
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        return await self._repo.get_items_for_section(db, s.id)

    async def create_item(self, db: AsyncSession, key: str, data: SectionItemCreate):
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        item = await self._repo.create_item(db, s.id, **data.model_dump())
        await db.commit()
        await db.refresh(item)
        return item

    async def update_item(
        self, db: AsyncSession, key: str, item_id: uuid.UUID, data: SectionItemUpdate
    ):
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        item = await self._repo.get_item(db, item_id)
        if not item or item.section_id != s.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        item = await self._repo.update_item(
            db, item, data.model_dump(exclude_unset=True)
        )
        await db.commit()
        await db.refresh(item)
        return item

    async def delete_item(self, db: AsyncSession, key: str, item_id: uuid.UUID) -> None:
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        item = await self._repo.get_item(db, item_id)
        if not item or item.section_id != s.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        await self._repo.delete_item(db, item)
        await db.commit()

    async def reorder_items(
        self, db: AsyncSession, key: str, entries: list[SectionItemReorderEntry]
    ) -> None:
        s = await self._repo.get_section_by_key(db, key)
        if not s:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
        await self._repo.reorder_items(
            db, [{"id": e.id, "sort_order": e.sort_order} for e in entries]
        )
        await db.commit()

    # ── Media ──────────────────────────────────────────────────────────────────

    async def list_media(
        self,
        db: AsyncSession,
        folder: str | None = None,
        mime_prefix: str | None = None,
        page: int = 1,
        page_size: int = 48,
    ) -> tuple[list[CmsMedia], int]:
        return await self._repo.list_media(db, folder, mime_prefix, page, page_size)

    async def update_media(
        self, db: AsyncSession, media_id: uuid.UUID, data: CmsMediaUpdate
    ) -> CmsMedia:
        m = await self._repo.get_media(db, media_id)
        if not m:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
        m = await self._repo.update_media(db, m, data.model_dump(exclude_unset=True))
        await db.commit()
        await db.refresh(m)
        return m

    async def delete_media(self, db: AsyncSession, media_id: uuid.UUID) -> None:
        m = await self._repo.get_media(db, media_id)
        if not m:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
        await self._repo.delete_media(db, m)
        await db.commit()

    # ── Publish log ────────────────────────────────────────────────────────────

    async def get_publish_log(self, db: AsyncSession, limit: int = 50) -> list:
        return await self._repo.get_publish_log(db, limit)

    # ── Legacy banner admin ────────────────────────────────────────────────────

    async def list_banners(self, db: AsyncSession) -> list[Banner]:
        return await self._repo.get_active_banners(db)

    async def create_banner(self, db: AsyncSession, data: BannerCreate) -> Banner:
        b = await self._repo.create_banner(db, **data.model_dump())
        await db.commit()
        await db.refresh(b)
        return b

    async def update_banner(
        self, db: AsyncSession, banner_id: uuid.UUID, data: BannerUpdate
    ) -> Banner:
        b = await self._repo.get_banner(db, banner_id)
        if not b:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Banner not found")
        b = await self._repo.update_banner(db, b, data.model_dump(exclude_unset=True))
        await db.commit()
        await db.refresh(b)
        return b

    async def delete_banner(self, db: AsyncSession, banner_id: uuid.UUID) -> None:
        b = await self._repo.get_banner(db, banner_id)
        if not b:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Banner not found")
        await self._repo.delete_banner(db, b)
        await db.commit()

    # ── Pages ──────────────────────────────────────────────────────────────────

    async def get_page(self, db: AsyncSession, slug: str) -> CmsPage:
        page = await self._repo.get_page(db, slug)
        if not page:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
        return page

    async def create_page(self, db: AsyncSession, data: CmsPageCreate) -> CmsPage:
        p = await self._repo.create_page(db, **data.model_dump())
        await db.commit()
        await db.refresh(p)
        return p

    async def update_page(
        self, db: AsyncSession, page_id: uuid.UUID, data: CmsPageUpdate
    ) -> CmsPage:
        p = await self._repo.get_page_by_id(db, page_id)
        if not p:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
        p = await self._repo.update_page(db, p, data.model_dump(exclude_unset=True))
        await db.commit()
        await db.refresh(p)
        return p
