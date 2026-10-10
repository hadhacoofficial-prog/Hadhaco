"""Hero slide video_url must be a playable file on a CSP-allowed host.

Regression: an Instagram profile URL was saved as a slide's video_url and
rendered into <video src>, which the storefront CSP (media-src) blocked.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.modules.cms.hero_validation import validate_hero_slide, video_url_problem
from app.modules.cms.schemas import SectionItemCreate, SectionItemUpdate
from app.modules.cms.service import CMSService


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "   ",
        "https://cdn.hadha.co/cms/hero/intro.mp4",
        "https://cdn.hadha.co/cms/hero/intro.webm?v=2",
        "https://videos.pexels.com/video-files/3571264/3571264-uhd.mp4",
        "/media/intro.mp4",
    ],
)
def test_valid_video_urls(url):
    assert video_url_problem(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/popula_dabba_?xtok=abc&utm_source=qr",
        "https://www.youtube.com/watch?v=abc",
        "https://example.com/video.mp4",  # blocked by CSP media-src
        "http://cdn.hadha.co/intro.mp4",  # not https
        "https://cdn.hadha.co/page",  # not a video file
        "//cdn.hadha.co/intro.mp4",  # protocol-relative
        "https://cdn.hadha.co.evil.com/intro.mp4",
    ],
)
def test_invalid_video_urls(url):
    assert video_url_problem(url)


def test_publish_validation_reports_video_error():
    slide = {
        "content": {"headline": "Hello"},
        "media": {
            "desktop_image_url": "https://cdn.hadha.co/a.jpg",
            "video_url": "https://www.instagram.com/x",
        },
        "colors": {},
        "buttons": {},
    }
    errors, _ = validate_hero_slide(slide, 0)
    assert any(e.field == "media.video_url" for e in errors)


def _svc_with_section(section_type: str) -> tuple[CMSService, AsyncMock]:
    svc = CMSService.__new__(CMSService)
    section = SimpleNamespace(id=uuid.uuid4(), section_type=section_type)
    repo = SimpleNamespace(
        get_section_by_key=AsyncMock(return_value=section),
        create_item=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        get_item=AsyncMock(return_value=SimpleNamespace(section_id=section.id)),
        update_item=AsyncMock(return_value=SimpleNamespace()),
    )
    svc._repo = repo  # type: ignore[attr-defined]
    return svc, repo.create_item


async def test_create_item_rejects_instagram_video_on_hero():
    svc, create = _svc_with_section("hero_carousel")
    db = AsyncMock()
    data = SectionItemCreate(
        config={"media": {"video_url": "https://www.instagram.com/x"}}
    )
    with pytest.raises(HTTPException) as exc:
        await svc.create_item(db, "hero_carousel", data)
    assert exc.value.status_code == 422
    create.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_update_item_rejects_legacy_flat_video_url():
    svc, _ = _svc_with_section("hero_carousel")
    data = SectionItemUpdate(config={"video_url": "https://www.instagram.com/x"})
    with pytest.raises(HTTPException) as exc:
        await svc.update_item(AsyncMock(), "hero_carousel", uuid.uuid4(), data)
    assert exc.value.status_code == 422


async def test_non_hero_sections_are_unaffected():
    svc, create = _svc_with_section("featured_products")
    data = SectionItemCreate(config={"media": {"video_url": "https://x.example/y"}})
    await svc.create_item(AsyncMock(), "featured", data)
    create.assert_awaited_once()
