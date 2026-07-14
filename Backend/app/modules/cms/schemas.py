from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Banners ───────────────────────────────────────────────────────────────────


class BannerOut(BaseModel):
    id: uuid.UUID
    name: str
    banner_type: str
    title: str | None
    subtitle: str | None
    cta_text: str | None
    cta_url: str | None
    desktop_image_url: str | None
    mobile_image_url: str | None
    sort_order: int
    model_config = {"from_attributes": True}


class BannerCreate(BaseModel):
    name: str
    banner_type: str = Field(..., pattern="^(hero|promo_strip|category_feature|popup)$")
    title: str | None = None
    subtitle: str | None = None
    cta_text: str | None = None
    cta_url: str | None = None
    desktop_image_url: str | None = None
    mobile_image_url: str | None = None
    sort_order: int = 0
    is_active: bool = True


class BannerUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    cta_text: str | None = None
    cta_url: str | None = None
    desktop_image_url: str | None = None
    mobile_image_url: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


# ── Section items ─────────────────────────────────────────────────────────────


class SectionItemOut(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    sort_order: int
    is_enabled: bool
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class SectionItemCreate(BaseModel):
    config: dict[str, Any] = {}
    sort_order: int = 0
    is_enabled: bool = True


class SectionItemUpdate(BaseModel):
    config: dict[str, Any] | None = None
    sort_order: int | None = None
    is_enabled: bool | None = None


class SectionItemReorderEntry(BaseModel):
    id: uuid.UUID
    sort_order: int


# ── Landing sections ──────────────────────────────────────────────────────────


class LandingSectionOut(BaseModel):
    id: uuid.UUID
    section_key: str
    section_type: str
    title: str | None
    subtitle: str | None
    config: dict[str, Any]
    is_active: bool
    sort_order: int
    model_config = {"from_attributes": True}


class AdminSectionOut(BaseModel):
    id: uuid.UUID
    section_key: str
    section_type: str
    title: str | None
    subtitle: str | None
    config: dict[str, Any]
    draft_config: dict[str, Any]
    is_active: bool
    sort_order: int
    status: str
    published_at: datetime | None
    scheduled_at: datetime | None
    version_number: int
    created_at: datetime
    updated_at: datetime
    items: list[SectionItemOut] = []
    model_config = {"from_attributes": True}


class LandingSectionUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class SaveDraftRequest(BaseModel):
    draft_config: dict[str, Any]
    change_summary: str | None = None


class PublishSectionRequest(BaseModel):
    change_summary: str | None = None
    scheduled_at: datetime | None = None
    acknowledge_warnings: bool = False


class HeroValidationErrorOut(BaseModel):
    type: Literal["error"] = "error"
    field: str
    message: str
    slide_index: int | None = None


class HeroValidationWarningOut(BaseModel):
    type: Literal["warning"] = "warning"
    field: str
    message: str
    slide_index: int | None = None


class HeroValidationResultOut(BaseModel):
    errors: list[HeroValidationErrorOut] = []
    warnings: list[HeroValidationWarningOut] = []


class ReorderSectionEntry(BaseModel):
    id: uuid.UUID
    sort_order: int


# ── Homepage public response ──────────────────────────────────────────────────


class SectionDataOut(BaseModel):
    config: dict[str, Any]
    items: list[SectionItemOut] = []


class LayoutSectionOut(BaseModel):
    section_key: str
    section_type: str
    sort_order: int
    is_active: bool
    title: str | None


class HomepageDataOut(BaseModel):
    cache_version: int
    layout: list[LayoutSectionOut]
    sections: dict[str, SectionDataOut]


# ── CMS Pages ─────────────────────────────────────────────────────────────────


class CmsPageOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    content: str
    is_active: bool
    seo_title: str | None
    seo_description: str | None
    model_config = {"from_attributes": True}


class CmsPageCreate(BaseModel):
    slug: str
    title: str
    content: str
    seo_title: str | None = None
    seo_description: str | None = None


class CmsPageUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    is_active: bool | None = None
    seo_title: str | None = None
    seo_description: str | None = None


# ── Legacy (kept for backward compat with GET /cms/home) ─────────────────────


class HomePageResponse(BaseModel):
    hero_banners: list[BannerOut] = []
    promo_strip: BannerOut | None = None
    sections: list[LandingSectionOut] = []


# ── Version history ───────────────────────────────────────────────────────────


class VersionHistoryOut(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    version_number: int
    config_snapshot: dict[str, Any]
    items_snapshot: list[Any]
    change_summary: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Media ─────────────────────────────────────────────────────────────────────


class CmsMediaOut(BaseModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    mime_type: str
    file_size: int
    width: int | None
    height: int | None
    duration: float | None
    cdn_url: str
    thumbnail_url: str | None
    folder: str
    alt_text: str | None
    tags: list[str]
    usage_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CmsMediaUpdate(BaseModel):
    alt_text: str | None = None
    folder: str | None = None
    tags: list[str] | None = None


class MediaListOut(BaseModel):
    items: list[CmsMediaOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Publish log ───────────────────────────────────────────────────────────────


class PublishLogOut(BaseModel):
    id: uuid.UUID
    action: str
    section_key: str | None
    admin_id: uuid.UUID | None
    extra_meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    model_config = {"from_attributes": True}
