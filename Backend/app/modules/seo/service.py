import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


class SeoService:

    async def get_page(self, db: AsyncSession, path: str) -> dict | None:
        result = await db.execute(
            text(
                "SELECT path, title, description, canonical_url, og_image, "
                "og_title, og_description, structured_data, noindex "
                "FROM seo_pages WHERE path = :path AND is_active = true"
            ),
            {"path": path},
        )
        row = result.fetchone()
        if not row:
            return None
        return dict(row._mapping)

    async def upsert_page(self, db: AsyncSession, data: dict[str, Any]) -> dict:
        result = await db.execute(
            text(
                "INSERT INTO seo_pages (id, path, title, description, canonical_url, "
                "og_image, og_title, og_description, structured_data, noindex, is_active) "
                "VALUES (gen_random_uuid(), :path, :title, :description, :canonical_url, "
                ":og_image, :og_title, :og_description, :structured_data, :noindex, true) "
                "ON CONFLICT (path) DO UPDATE SET "
                "title = EXCLUDED.title, description = EXCLUDED.description, "
                "canonical_url = EXCLUDED.canonical_url, og_image = EXCLUDED.og_image, "
                "og_title = EXCLUDED.og_title, og_description = EXCLUDED.og_description, "
                "structured_data = EXCLUDED.structured_data, noindex = EXCLUDED.noindex, "
                "updated_at = now() "
                "RETURNING *"
            ),
            data,
        )
        return dict(result.fetchone()._mapping)

    async def get_redirect(self, db: AsyncSession, from_path: str) -> str | None:
        result = await db.execute(
            text(
                "SELECT to_path FROM seo_redirects "
                "WHERE from_path = :from_path AND is_active = true"
            ),
            {"from_path": from_path},
        )
        row = result.fetchone()
        return row[0] if row else None

    async def create_redirect(
        self, db: AsyncSession, from_path: str, to_path: str, status_code: int = 301
    ) -> None:
        await db.execute(
            text(
                "INSERT INTO seo_redirects (id, from_path, to_path, status_code, is_active) "
                "VALUES (gen_random_uuid(), :from_path, :to_path, :status_code, true) "
                "ON CONFLICT (from_path) DO UPDATE SET "
                "to_path = EXCLUDED.to_path, status_code = EXCLUDED.status_code, "
                "is_active = true, updated_at = now()"
            ),
            {"from_path": from_path, "to_path": to_path, "status_code": status_code},
        )

    async def generate_sitemap(self, db: AsyncSession) -> str:
        """Generate XML sitemap for active products and categories."""
        base_url = settings.FRONTEND_URL.rstrip("/")
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]

        # Static pages
        for path in ["/", "/collections", "/categories"]:
            lines.append(f"  <url><loc>{base_url}{path}</loc><changefreq>weekly</changefreq></url>")

        # Active products
        products = await db.execute(
            text("SELECT slug, updated_at FROM products WHERE status = 'active' AND deleted_at IS NULL")
        )
        for row in products.fetchall():
            lastmod = row[1].strftime("%Y-%m-%d") if row[1] else ""
            lines.append(
                f"  <url><loc>{base_url}/products/{row[0]}</loc>"
                f"<lastmod>{lastmod}</lastmod>"
                f"<changefreq>weekly</changefreq></url>"
            )

        # Active categories
        cats = await db.execute(
            text("SELECT slug FROM categories WHERE is_active = true AND deleted_at IS NULL")
        )
        for row in cats.fetchall():
            lines.append(
                f"  <url><loc>{base_url}/categories/{row[0]}</loc>"
                f"<changefreq>monthly</changefreq></url>"
            )

        lines.append("</urlset>")
        return "\n".join(lines)
