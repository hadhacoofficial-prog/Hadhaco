"""Brand context injected into every notification render.

Identity values mirror the storefront's single source of truth
(`Frontend_whole/packages/shared-utils/src/config/brand.ts`) and its routes
(`constants/routes.ts`), so notifications read as the same brand voice.

Resolution order per value (highest wins):
1. Event context (merged on top of this dict by the service)
2. CMS "footer" section config — the same `landing_sections` row the
   storefront Footer/Header render from (logo_url, company_address, phone,
   email, instagram, youtube, facebook, copyright_name, description)
3. Environment settings (BRAND_*/SUPPORT_*/SOCIAL_*)
4. Hardcoded storefront BRAND defaults (via the settings defaults)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = structlog.get_logger(__name__)


def get_brand_context() -> dict[str, Any]:
    base = settings.FRONTEND_URL.rstrip("/")
    return {
        # Identity — mirrors packages/shared-utils config/brand.ts
        "brand_name": settings.BRAND_NAME,
        "brand_short_name": settings.BRAND_SHORT_NAME,
        "brand_legal_name": settings.BRAND_LEGAL_NAME,
        "brand_tagline": settings.BRAND_TAGLINE,
        "brand_description": settings.BRAND_DESCRIPTION,
        "brand_logo_url": settings.BRAND_LOGO_URL,
        "brand_logo_dark_url": settings.BRAND_LOGO_DARK_URL,
        "brand_address": settings.BRAND_ADDRESS,
        "current_year": datetime.now(UTC).year,
        # Support
        "support_email": settings.SUPPORT_EMAIL,
        "support_phone": settings.SUPPORT_PHONE,
        # Social
        "social_instagram": settings.SOCIAL_INSTAGRAM_URL,
        "social_facebook": settings.SOCIAL_FACEBOOK_URL,
        "social_youtube": settings.SOCIAL_YOUTUBE_URL,
        # Deep links — storefront ROUTES, derived from FRONTEND_URL so staging
        # environments never link to production. Every route verified against
        # the storefront route tree (see Docs/Notification_docs/URL_AUDIT.md).
        "frontend_url": base,
        "website_label": base.split("://", 1)[-1],
        "shop_url": f"{base}/collections",
        "new_arrivals_url": f"{base}/search?filter=new",
        "account_url": f"{base}/account",
        "orders_url": f"{base}/account?tab=orders",
        "order_url": f"{base}/account?tab=orders",
        "cart_url": f"{base}/cart",
        "contact_url": f"{base}/contact",
        "returns_url": f"{base}/shipping-returns",
        "privacy_url": f"{base}/privacy",
        "terms_url": f"{base}/terms",
        "admin_url": settings.ADMIN_URL.rstrip("/"),
    }


# CMS footer config key → brand context key (same mapping Footer.tsx applies)
_CMS_FOOTER_MAP = {
    "logo_url": "brand_logo_dark_url",  # footer logo is the on-dark variant
    "company_address": "brand_address",
    "phone": "support_phone",
    "email": "support_email",
    "instagram": "social_instagram",
    "youtube": "social_youtube",
    "facebook": "social_facebook",
    "copyright_name": "brand_legal_name",
    "description": "brand_description",
}


async def get_brand_context_db(db: AsyncSession) -> dict[str, Any]:
    """Brand context with the CMS footer overlay.

    The storefront header/footer render from the CMS `footer` section; emails
    read the same published config so admin edits propagate to notifications
    without a deploy. Any CMS failure degrades to env/static defaults —
    notifications must never fail because of CMS state.
    """
    ctx = get_brand_context()
    try:
        from app.modules.cms.models import LandingSection

        result = await db.execute(
            select(LandingSection.config).where(
                LandingSection.section_key == "footer",
                LandingSection.is_active.is_(True),
            )
        )
        config = result.scalar_one_or_none() or {}
        for cms_key, ctx_key in _CMS_FOOTER_MAP.items():
            value = config.get(cms_key)
            if value:
                ctx[ctx_key] = value
    except Exception as exc:
        logger.warning("brand_context_cms_overlay_failed", error=str(exc))
    return ctx
