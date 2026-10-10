import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.status import compute_inventory_status


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

        # One statement returns the page AND the total (COUNT(*) OVER()), so a
        # normal search is a single round trip to the DB instead of count +
        # items. Each extra statement costs ~100-250ms against the remote DB.
        total, items = await self._page(
            db,
            where_sql,
            params,
            page,
            select_extra=(
                "ts_rank(p.search_vector, plainto_tsquery('english', :query)) "
                "AS rank"
            ),
            order_sql="rank DESC, p.id",
        )

        if total == 0:
            # Fallback: ILIKE
            params["ilike"] = f"%{safe_query}%"
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

            total, items = await self._page(
                db,
                " AND ".join(fallback_where),
                params,
                page,
                select_extra=None,
                order_sql="p.created_at DESC, p.id",
            )

        for item in items:
            inventory_status, can_purchase = compute_inventory_status(
                item["available_stock"],
                item["low_stock_threshold"],
                item["track_inventory"],
                item["allow_backorder"],
            )
            item["inventory_status"] = inventory_status.value
            item["can_purchase"] = can_purchase

        import math

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size) if total else 0,
        }

    async def _page(
        self,
        db: AsyncSession,
        where_sql: str,
        params: dict[str, Any],
        page: int,
        *,
        select_extra: str | None,
        order_sql: str,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Fetch one page of matches plus the total match count.

        ``COUNT(*) OVER()`` rides on the returned rows, so a page past the end
        reports no total; only then (page > 1 and no rows) pay for a plain
        count so callers can tell "page too far" from "no results".
        """
        extra = f", {select_extra}" if select_extra else ""
        items_sql = text(
            "SELECT p.id, p.name, p.slug, p.base_price, p.compare_at_price, "  # nosec B608
            "vs.available_stock, "
            "p.low_stock_threshold, p.track_inventory, p.allow_backorder, "
            f"p.metal_type, p.is_featured{extra}, "
            "COUNT(*) OVER() AS _total "
            "FROM products p "
            "LEFT JOIN LATERAL ("
            "    SELECT COALESCE(SUM(GREATEST(v.stock_quantity - v.reserved_quantity"
            "    - v.sold_quantity, 0)), 0) AS available_stock"  # mirrors compute_available_stock()
            "    FROM product_variants v"
            "    WHERE v.product_id = p.id AND v.is_active = true"
            ") vs ON true "
            f"WHERE {where_sql} "
            f"ORDER BY {order_sql} OFFSET :offset LIMIT :limit"
        )
        rows = (await db.execute(items_sql, params)).fetchall()
        if rows:
            mappings = [dict(r._mapping) for r in rows]
            total = int(mappings[0]["_total"])
            for m in mappings:
                m.pop("_total", None)
            return total, mappings
        if page <= 1:
            return 0, []
        count = await db.execute(
            text(f"SELECT COUNT(*) FROM products p WHERE {where_sql}"),  # nosec B608
            params,
        )
        return int(count.scalar_one()), []

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
