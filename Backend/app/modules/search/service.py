import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SearchService:
    async def full_text_search(
        self,
        db: AsyncSession,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20,
        category_id: uuid.UUID | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> dict[str, Any]:
        """
        Full-text product search using PostgreSQL tsvector.
        Falls back to ILIKE if no FTS results.
        """
        if not query or not query.strip():
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

        safe_query = query.strip()[:200]
        offset = (page - 1) * page_size

        # Build tsquery — use plainto_tsquery for natural input
        params: dict[str, Any] = {
            "query": safe_query,
            "offset": offset,
            "limit": page_size,
            "status": "active",
        }

        where_clauses = [
            "p.deleted_at IS NULL",
            "p.status = :status",
            "p.search_vector @@ plainto_tsquery('english', :query)",
        ]

        if category_id:
            where_clauses.append("p.category_id = :category_id")
            params["category_id"] = str(category_id)
        if min_price is not None:
            where_clauses.append("p.base_price >= :min_price")
            params["min_price"] = min_price
        if max_price is not None:
            where_clauses.append("p.base_price <= :max_price")
            params["max_price"] = max_price

        where_sql = " AND ".join(where_clauses)

        count_sql = text(
            f"SELECT COUNT(*) FROM products p WHERE {where_sql}"  # nosec B608
        )
        total_result = await db.execute(count_sql, params)
        total: int = total_result.scalar_one()

        if total == 0:
            # Fallback: ILIKE
            ilike_term = f"%{safe_query}%"
            params["ilike"] = ilike_term
            fallback_where = [
                "p.deleted_at IS NULL",
                "p.status = :status",
                "(p.name ILIKE :ilike OR p.description ILIKE :ilike OR p.sku ILIKE :ilike)",
            ]
            if category_id:
                fallback_where.append("p.category_id = :category_id")
            if min_price is not None:
                fallback_where.append("p.base_price >= :min_price")
            if max_price is not None:
                fallback_where.append("p.base_price <= :max_price")

            fallback_sql = " AND ".join(fallback_where)
            count_fb = await db.execute(
                text(f"SELECT COUNT(*) FROM products p WHERE {fallback_sql}"),  # nosec
                params,
            )
            total = count_fb.scalar_one()

            items_sql = text(
                f"SELECT p.id, p.name, p.slug, p.base_price, p.compare_at_price, "  # nosec B608
                f"p.stock_quantity, p.metal_type, p.is_featured "
                f"FROM products p WHERE {fallback_sql} "
                f"ORDER BY p.created_at DESC OFFSET :offset LIMIT :limit"
            )
        else:
            items_sql = text(
                f"SELECT p.id, p.name, p.slug, p.base_price, p.compare_at_price, "  # nosec B608
                f"p.stock_quantity, p.metal_type, p.is_featured, "
                f"ts_rank(p.search_vector, plainto_tsquery('english', :query)) AS rank "
                f"FROM products p WHERE {where_sql} "
                f"ORDER BY rank DESC OFFSET :offset LIMIT :limit"
            )

        rows = await db.execute(items_sql, params)
        items = [dict(r._mapping) for r in rows.fetchall()]

        import math

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size) if total else 0,
        }

    async def autocomplete(
        self, db: AsyncSession, query: str, limit: int = 8
    ) -> list[str]:
        """Return product name suggestions for autocomplete."""
        if not query or len(query) < 2:
            return []
        term = f"{query.strip()[:50]}%"
        result = await db.execute(
            text(
                "SELECT DISTINCT name FROM products "
                "WHERE deleted_at IS NULL AND status = 'active' AND name ILIKE :term "
                "ORDER BY name LIMIT :limit"
            ),
            {"term": term, "limit": limit},
        )
        return [row[0] for row in result.fetchall()]

    async def record_search(
        self,
        db: AsyncSession,
        query: str,
        user_id: str | None,
        result_count: int,
    ) -> None:
        """Persist search history."""
        if not query or not query.strip():
            return
        await db.execute(
            text(
                "INSERT INTO search_history (id, user_id, query, result_count, created_at) "
                "VALUES (gen_random_uuid(), :user_id, :query, :result_count, now())"
            ),
            {
                "user_id": user_id,
                "query": query.strip()[:200],
                "result_count": result_count,
            },
        )

    async def trending_searches(self, db: AsyncSession, limit: int = 10) -> list[dict]:
        """Top searches from the materialized view (refreshed by scheduler).

        Falls back to a live aggregation from search_history when the
        materialized view hasn't been created yet.
        """
        try:
            result = await db.execute(
                text(
                    "SELECT query, search_count FROM trending_searches "
                    "ORDER BY search_count DESC LIMIT :limit"
                ),
                {"limit": limit},
            )
            return [{"query": row[0], "count": row[1]} for row in result.fetchall()]
        except Exception:
            pass
        try:
            result = await db.execute(
                text(
                    "SELECT query, COUNT(*) AS search_count "
                    "FROM search_history "
                    "WHERE created_at >= NOW() - INTERVAL '7 days' "
                    "GROUP BY query "
                    "ORDER BY search_count DESC LIMIT :limit"
                ),
                {"limit": limit},
            )
            return [{"query": row[0], "count": row[1]} for row in result.fetchall()]
        except Exception:
            return []
