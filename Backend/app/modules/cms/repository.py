from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cms.models import (
    AppSetting,
    Banner,
    CmsMedia,
    CmsPage,
    CmsPublishLog,
    CmsSectionItem,
    CmsVersionHistory,
    LandingSection,
)


class CMSRepository:
    # ── Banners ────────────────────────────────────────────────────────────────

    async def get_active_banners(
        self, db: AsyncSession, banner_type: str | None = None
    ) -> list[Banner]:
        q = select(Banner).where(Banner.is_active.is_(True), Banner.deleted_at.is_(None))
        if banner_type:
            q = q.where(Banner.banner_type == banner_type)
        result = await db.execute(q.order_by(Banner.sort_order))
        return list(result.scalars().all())

    async def get_banner(self, db: AsyncSession, banner_id: uuid.UUID) -> Banner | None:
        result = await db.execute(
            select(Banner).where(Banner.id == banner_id, Banner.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def create_banner(self, db: AsyncSession, **kwargs: Any) -> Banner:
        b = Banner(**kwargs)
        db.add(b)
        await db.flush()
        return b

    async def update_banner(self, db: AsyncSession, banner: Banner, data: dict[str, Any]) -> Banner:
        for k, v in data.items():
            setattr(banner, k, v)
        db.add(banner)
        await db.flush()
        return banner

    async def delete_banner(self, db: AsyncSession, banner: Banner) -> None:
        banner.deleted_at = datetime.now(UTC)
        db.add(banner)
        await db.flush()

    # ── Landing sections ───────────────────────────────────────────────────────

    async def get_active_sections(self, db: AsyncSession) -> list[LandingSection]:
        result = await db.execute(
            select(LandingSection)
            .where(LandingSection.is_active.is_(True))
            .order_by(LandingSection.sort_order)
        )
        return list(result.scalars().all())

    async def get_all_sections(self, db: AsyncSession) -> list[LandingSection]:
        result = await db.execute(select(LandingSection).order_by(LandingSection.sort_order))
        return list(result.scalars().all())

    async def get_section_by_key(self, db: AsyncSession, key: str) -> LandingSection | None:
        result = await db.execute(select(LandingSection).where(LandingSection.section_key == key))
        return result.scalar_one_or_none()

    async def get_section_by_id(
        self, db: AsyncSession, section_id: uuid.UUID
    ) -> LandingSection | None:
        result = await db.execute(select(LandingSection).where(LandingSection.id == section_id))
        return result.scalar_one_or_none()

    async def update_section(
        self, db: AsyncSession, section: LandingSection, data: dict[str, Any]
    ) -> LandingSection:
        for k, v in data.items():
            setattr(section, k, v)
        section.updated_at = datetime.now(UTC)
        db.add(section)
        await db.flush()
        return section

    async def reorder_sections(self, db: AsyncSession, entries: list[dict]) -> None:
        for entry in entries:
            await db.execute(
                update(LandingSection)
                .where(LandingSection.id == entry["id"])
                .values(sort_order=entry["sort_order"], updated_at=datetime.now(UTC))
            )

    # ── Section items ──────────────────────────────────────────────────────────

    async def get_items_for_section(
        self, db: AsyncSession, section_id: uuid.UUID
    ) -> list[CmsSectionItem]:
        result = await db.execute(
            select(CmsSectionItem)
            .where(CmsSectionItem.section_id == section_id)
            .order_by(CmsSectionItem.sort_order)
        )
        return list(result.scalars().all())

    async def get_item(self, db: AsyncSession, item_id: uuid.UUID) -> CmsSectionItem | None:
        result = await db.execute(select(CmsSectionItem).where(CmsSectionItem.id == item_id))
        return result.scalar_one_or_none()

    async def create_item(
        self, db: AsyncSession, section_id: uuid.UUID, **kwargs: Any
    ) -> CmsSectionItem:
        item = CmsSectionItem(section_id=section_id, **kwargs)
        db.add(item)
        await db.flush()
        return item

    async def update_item(
        self, db: AsyncSession, item: CmsSectionItem, data: dict[str, Any]
    ) -> CmsSectionItem:
        for k, v in data.items():
            setattr(item, k, v)
        item.updated_at = datetime.now(UTC)
        db.add(item)
        await db.flush()
        return item

    async def delete_item(self, db: AsyncSession, item: CmsSectionItem) -> None:
        await db.delete(item)
        await db.flush()

    async def reorder_items(self, db: AsyncSession, entries: list[dict]) -> None:
        for entry in entries:
            await db.execute(
                update(CmsSectionItem)
                .where(CmsSectionItem.id == entry["id"])
                .values(sort_order=entry["sort_order"], updated_at=datetime.now(UTC))
            )

    # ── Version history ────────────────────────────────────────────────────────

    async def create_version(
        self,
        db: AsyncSession,
        section_id: uuid.UUID,
        version_number: int,
        config_snapshot: dict,
        items_snapshot: list,
        published_by: uuid.UUID | None,
        change_summary: str | None,
    ) -> CmsVersionHistory:
        v = CmsVersionHistory(
            section_id=section_id,
            version_number=version_number,
            config_snapshot=config_snapshot,
            items_snapshot=items_snapshot,
            published_by=published_by,
            change_summary=change_summary,
        )
        db.add(v)
        await db.flush()
        return v

    async def get_versions(
        self, db: AsyncSession, section_id: uuid.UUID
    ) -> list[CmsVersionHistory]:
        result = await db.execute(
            select(CmsVersionHistory)
            .where(CmsVersionHistory.section_id == section_id)
            .order_by(CmsVersionHistory.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_version(
        self, db: AsyncSession, version_id: uuid.UUID
    ) -> CmsVersionHistory | None:
        result = await db.execute(
            select(CmsVersionHistory).where(CmsVersionHistory.id == version_id)
        )
        return result.scalar_one_or_none()

    # ── Publish log ────────────────────────────────────────────────────────────

    async def create_publish_log(
        self,
        db: AsyncSession,
        action: str,
        section_key: str | None,
        admin_id: uuid.UUID | None,
        metadata: dict,
    ) -> CmsPublishLog:
        entry = CmsPublishLog(
            action=action,
            section_key=section_key,
            admin_id=admin_id,
            extra_meta=metadata,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def get_publish_log(self, db: AsyncSession, limit: int = 50) -> list[CmsPublishLog]:
        result = await db.execute(
            select(CmsPublishLog).order_by(CmsPublishLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    # ── Media ──────────────────────────────────────────────────────────────────

    async def create_media(self, db: AsyncSession, **kwargs: Any) -> CmsMedia:
        m = CmsMedia(**kwargs)
        db.add(m)
        await db.flush()
        return m

    async def get_media(self, db: AsyncSession, media_id: uuid.UUID) -> CmsMedia | None:
        result = await db.execute(
            select(CmsMedia).where(CmsMedia.id == media_id, CmsMedia.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_media(
        self,
        db: AsyncSession,
        folder: str | None = None,
        mime_prefix: str | None = None,
        page: int = 1,
        page_size: int = 48,
    ) -> tuple[list[CmsMedia], int]:
        q = select(CmsMedia).where(CmsMedia.deleted_at.is_(None))
        if folder:
            q = q.where(CmsMedia.folder == folder)
        if mime_prefix:
            q = q.where(CmsMedia.mime_type.like(f"{mime_prefix}%"))
        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()
        result = await db.execute(
            q.order_by(CmsMedia.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def update_media(
        self, db: AsyncSession, media: CmsMedia, data: dict[str, Any]
    ) -> CmsMedia:
        for k, v in data.items():
            setattr(media, k, v)
        media.updated_at = datetime.now(UTC)
        db.add(media)
        await db.flush()
        return media

    async def delete_media(self, db: AsyncSession, media: CmsMedia) -> None:
        media.deleted_at = datetime.now(UTC)
        db.add(media)
        await db.flush()

    # ── CMS Pages ─────────────────────────────────────────────────────────────

    async def get_page(self, db: AsyncSession, slug: str) -> CmsPage | None:
        result = await db.execute(
            select(CmsPage).where(
                CmsPage.slug == slug,
                CmsPage.is_active.is_(True),
                CmsPage.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_page(self, db: AsyncSession, **kwargs: Any) -> CmsPage:
        p = CmsPage(**kwargs)
        db.add(p)
        await db.flush()
        return p

    async def update_page(self, db: AsyncSession, page: CmsPage, data: dict[str, Any]) -> CmsPage:
        for k, v in data.items():
            setattr(page, k, v)
        db.add(page)
        await db.flush()
        return page

    async def get_page_by_id(self, db: AsyncSession, page_id: uuid.UUID) -> CmsPage | None:
        result = await db.execute(
            select(CmsPage).where(CmsPage.id == page_id, CmsPage.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    # ── App settings ───────────────────────────────────────────────────────────

    async def get_setting(self, db: AsyncSession, key: str) -> AppSetting | None:
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        return result.scalar_one_or_none()

    async def get_public_settings(self, db: AsyncSession) -> list[AppSetting]:
        result = await db.execute(select(AppSetting).where(AppSetting.is_public.is_(True)))
        return list(result.scalars().all())

    async def get_all_settings(self, db: AsyncSession) -> list[AppSetting]:
        result = await db.execute(select(AppSetting))
        return list(result.scalars().all())
