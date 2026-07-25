"""Brand context injected into every notification render.

Resolution order per value (highest wins):
1. Event context (merged on top of this dict by the service)
2. CompanyConfig (admin-managed singleton — the single source of truth)
3. CMS "footer" section config — the same `landing_sections` row the
   storefront Footer/Header render from (logo_url, company_address, phone,
   email, instagram, youtube, facebook, copyright_name, description)
4. Environment settings (BRAND_*/SUPPORT_*/SOCIAL_*)
5. Hardcoded storefront BRAND defaults (via the settings defaults)
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


# CompanyConfig field → brand context key
_COMPANY_CONFIG_MAP = {
    "name": "brand_name",
    "brand_name": "brand_short_name",
    "legal_name": "brand_legal_name",
    "tagline": "brand_tagline",
    "description": "brand_description",
    "logo_url": "brand_logo_url",
    "address_line_1": "brand_address",
    "support_email": "support_email",
    "phone": "support_phone",
    "instagram_url": "social_instagram",
    "facebook_url": "social_facebook",
    "youtube_url": "social_youtube",
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
    """Brand context with CompanyConfig + CMS footer overlay.

    CompanyConfig is the primary source (admin-managed singleton).
    CMS footer config overlays on top for fields it provides.
    Any failure degrades to env/static defaults.
    """
    ctx = get_brand_context()

    # Layer 1: CompanyConfig (highest priority)
    try:
        from app.modules.company.models import CompanyConfig

        result = await db.execute(select(CompanyConfig).where(CompanyConfig.id == 1))
        config = result.scalar_one_or_none()
        if config:
            for db_field, ctx_key in _COMPANY_CONFIG_MAP.items():
                value = getattr(config, db_field, None)
                if value:
                    ctx[ctx_key] = value
            # Build full address from components
            addr_parts = [
                getattr(config, "address_line_1", None),
                getattr(config, "address_line_2", None),
                getattr(config, "city", None),
                getattr(config, "state", None),
                getattr(config, "postal_code", None),
            ]
            full_address = ", ".join(p for p in addr_parts if p)
            if full_address:
                ctx["brand_address"] = full_address
    except Exception as exc:
        logger.warning("brand_context_company_config_failed", error=str(exc))

    # Layer 2: CMS footer overlay (for backward compatibility)
    try:
        from app.modules.cms.models import LandingSection

        cms_result = await db.execute(
            select(LandingSection.config).where(
                LandingSection.section_key == "footer",
                LandingSection.is_active.is_(True),
            )
        )
        cms_config: dict[str, Any] = cms_result.scalar_one_or_none() or {}
        for cms_key, ctx_key in _CMS_FOOTER_MAP.items():
            value = cms_config.get(cms_key)
            if value:
                ctx[ctx_key] = value
    except Exception as exc:
        logger.warning("brand_context_cms_overlay_failed", error=str(exc))

    return ctx
