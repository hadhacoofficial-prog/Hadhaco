"""Sitemap: serve valid XML (not the warmer's compressed blob) and list only
URLs the storefront actually serves.

Production regression (2026-10-10): /api/v1/sitemap.xml returned
"\\x01x\\x9c..." binary because the cache warmer stores big payloads
zlib-compressed and the router returned the raw cached string; it also listed
/categories and /categories/{slug}, which the storefront has no route for.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.core.cache import _compress_value
from app.core.model_registry import import_all_models

import_all_models()

from app.modules.seo import router as seo_router  # noqa: E402
from app.modules.seo.service import SeoService  # noqa: E402


class _Redis:
    def __init__(self, value: str) -> None:
        self.value = value

    async def get(self, key: str):
        return self.value

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.value = value


def _xml(n: int = 400) -> str:
    urls = "\n".join(
        f"  <url><loc>https://hadha.co/products/item-{i}</loc></url>" for i in range(n)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>"
    )


async def test_router_decompresses_warmer_written_entry(monkeypatch):
    xml = _xml()
    stored = _compress_value(xml)
    assert stored.startswith("\x01")  # what the warmer actually writes

    # Hermetic: don't depend on the process-wide Redis circuit-breaker state
    # (another test can leave it open, making safe_redis_get return None).
    monkeypatch.setattr(seo_router, "safe_redis_get", AsyncMock(return_value=stored))

    request = MagicMock()
    request.headers = {}
    resp = await seo_router.sitemap(
        request=request, db=MagicMock(), redis=_Redis(stored)
    )

    body = resp.body.decode("utf-8")
    assert body.startswith("<?xml")
    assert body == xml


def _rows(rows):
    res = MagicMock()
    res.fetchall.return_value = rows
    return res


async def test_generated_sitemap_has_only_real_storefront_routes(monkeypatch):
    monkeypatch.setattr(
        "app.modules.seo.service.settings",
        SimpleNamespace(FRONTEND_URL="https://hadha.co/"),
    )
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _rows([("silver-ring", datetime(2026, 10, 1))]),  # products
            _rows([("women-collection",)]),  # collections
        ]
    )

    xml = await SeoService().generate_sitemap(db)

    assert "/categories" not in xml
    assert "<loc>https://hadha.co/products/silver-ring</loc>" in xml
    assert "<loc>https://hadha.co/collections/women-collection</loc>" in xml
    for path in ("/", "/products", "/collections", "/about", "/terms"):
        assert f"<loc>https://hadha.co{path}</loc>" in xml
