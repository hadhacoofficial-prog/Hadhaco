"""
Promote CMS sections whose status='scheduled' and scheduled_at <= now() to published.
Runs every 60 seconds so sections go live within a minute of their scheduled time.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from app.core.database import AsyncWorkerSessionLocal
from app.core.redis import get_redis_pool
from app.modules.cms.models import LandingSection

log = structlog.get_logger(__name__)

_HOMEPAGE_CACHE_KEY = "cms:homepage"


async def run() -> None:
    t0 = time.perf_counter()
    try:
        now = datetime.now(UTC)

        async with AsyncWorkerSessionLocal() as db:
            result = await db.execute(
                select(LandingSection).where(
                    LandingSection.status == "scheduled",
                    LandingSection.scheduled_at <= now,
                )
            )
            sections = result.scalars().all()

            if not sections:
                return

            published = 0
            for section in sections:
                try:
                    section.config = section.draft_config or section.config
                    section.status = "published"
                    section.published_at = now
                    section.version_number = (section.version_number or 0) + 1
                    published += 1
                except Exception:
                    log.exception(
                        "cms_publish_section_failed", section_key=section.section_key
                    )

            await db.commit()

            if published:
                try:
                    redis = get_redis_pool()
                    await redis.delete(_HOMEPAGE_CACHE_KEY)
                except Exception:
                    log.warning("cms_publish_cache_clear_failed")

        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info("cms_publish_completed", published=published, duration_ms=duration_ms)

    except Exception:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.exception("cms_publish_failed", duration_ms=duration_ms)
