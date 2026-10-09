"""Site-wide list sorting & filtering: allowlists, filter clauses, parsing.

These compile the generated SQL (PostgreSQL dialect) instead of hitting a DB,
so they pin the safety properties — unknown sort keys never reach SQL,
every ordering has a deterministic tie-breaker, and facet groups can be
dropped independently.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.model_registry import import_all_models

import_all_models()

from app.modules.catalog.models import Product  # noqa: E402
from app.modules.catalog.repository import (  # noqa: E402
    ProductFilterSpec,
    _filter_clauses,
    _product_order_by,
)
from app.modules.catalog.router import _csv  # noqa: E402


def _sql(*order_by) -> str:
    q = select(Product.id).order_by(*order_by)
    return str(q.compile(dialect=postgresql.dialect()))


# ── _csv ─────────────────────────────────────────────────────────────────────


class TestCsvParam:
    def test_none_and_blank(self):
        assert _csv(None) is None
        assert _csv("") is None
        assert _csv(" , ,") is None

    def test_splits_trims_dedupes(self):
        assert _csv("rings, chains,rings") == ["rings", "chains"]

    def test_allowlist_drops_unknown(self):
        allowed = frozenset({"women", "men"})
        assert _csv("women,aliens", allowed=allowed) == ["women"]
        assert _csv("aliens", allowed=allowed) is None

    def test_caps_item_count_and_length(self):
        assert len(_csv(",".join(f"v{i}" for i in range(50))) or []) == 20
        assert _csv("x" * 101) is None


# ── Sorting ──────────────────────────────────────────────────────────────────


class TestProductOrderBy:
    @pytest.mark.parametrize(
        "key",
        [
            "created_at",
            "updated_at",
            "base_price",
            "name",
            "average_rating",
            "sold_quantity",
            "discount",
            "featured",
            "relevance",
        ],
    )
    def test_every_sort_ends_with_id_tiebreaker(self, key):
        clauses = _product_order_by(key, "desc", None)
        sql = _sql(*clauses)
        assert sql.rstrip().endswith("products.id")

    def test_unknown_key_falls_back_to_created_at(self):
        sql = _sql(*_product_order_by("password; DROP TABLE x", "asc", None))
        assert "products.created_at ASC" in sql
        assert "DROP" not in sql

    def test_price_direction(self):
        assert "base_price ASC" in _sql(*_product_order_by("base_price", "asc", None))
        assert "base_price DESC" in _sql(*_product_order_by("base_price", "desc", None))

    def test_relevance_uses_ts_rank_only_with_search(self):
        assert "ts_rank" in _sql(*_product_order_by("relevance", "desc", "chain"))
        no_q = _sql(*_product_order_by("relevance", "desc", None))
        assert "ts_rank" not in no_q
        assert "is_featured DESC" in no_q

    def test_rating_puts_unrated_last(self):
        sql = _sql(*_product_order_by("average_rating", "desc", None))
        assert "average_rating DESC NULLS LAST" in sql


# ── Filtering ────────────────────────────────────────────────────────────────


class TestFilterClauses:
    def test_default_only_excludes_deleted(self):
        assert set(_filter_clauses(ProductFilterSpec())) == {"deleted"}

    def test_groups_are_keyed_for_disjunctive_facets(self):
        spec = ProductFilterSpec(
            status="active",
            category_ids=[uuid.uuid4()],
            genders=["women", "men"],
            metal_types=["925 Silver"],
            purities=["925"],
            min_price=100,
            max_price=900,
            in_stock=True,
            on_sale=True,
            min_rating=4,
            is_new_arrival=True,
            is_best_seller=True,
            search="chain",
        )
        assert set(_filter_clauses(spec)) == {
            "deleted",
            "status",
            "category",
            "gender",
            "metal",
            "purity",
            "price",
            "in_stock",
            "on_sale",
            "rating",
            "new",
            "bestseller",
            "search",
        }

    def test_empty_category_ids_matches_nothing(self):
        clause = _filter_clauses(ProductFilterSpec(category_ids=[]))["category"]
        assert "false" in str(clause.compile(dialect=postgresql.dialect())).lower()

    def test_single_value_params_still_supported(self):
        c = _filter_clauses(ProductFilterSpec(gender="women", metal_type="Gold"))
        assert "gender" in c and "metal" in c

    def test_multi_value_uses_in(self):
        c = _filter_clauses(ProductFilterSpec(genders=["women", "men"]))["gender"]
        assert " IN " in str(c.compile(dialect=postgresql.dialect()))

    def test_stock_status_unknown_value_ignored(self):
        assert "stock_status" not in _filter_clauses(
            ProductFilterSpec(stock_status="bogus")
        )

    def test_cache_params_are_json_stable(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        p1 = ProductFilterSpec(category_ids=[a, b]).cache_params()
        p2 = ProductFilterSpec(category_ids=[b, a]).cache_params()
        assert p1 == p2
        assert all(isinstance(x, str) for x in p1["category_ids"])


# ── Admin list allowlists ────────────────────────────────────────────────────


class TestAdminOrderSort:
    async def test_unknown_sort_key_falls_back(self):
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        count = MagicMock()
        count.scalar_one.return_value = 0
        rows = MagicMock()
        rows.all.return_value = []
        db.execute = AsyncMock(side_effect=[count, rows])
        await OrderRepository().list_all(db, sort_by="evil", sort_dir="asc")
        sql = str(db.execute.await_args_list[1].args[0])
        assert "ORDER BY orders.created_at ASC, orders.id" in sql

    async def test_filters_and_sort_by_total(self):
        from datetime import UTC, datetime

        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        count = MagicMock()
        count.scalar_one.return_value = 0
        rows = MagicMock()
        rows.all.return_value = []
        db.execute = AsyncMock(side_effect=[count, rows])
        await OrderRepository().list_all(
            db,
            search="HDH",
            payment_status="paid",
            fulfillment_status="pending",
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to=datetime(2026, 2, 1, tzinfo=UTC),
            min_total=100,
            max_total=500,
            sort_by="total",
            sort_dir="desc",
        )
        sql = str(db.execute.await_args_list[1].args[0])
        assert "ORDER BY orders.total DESC, orders.id" in sql
        for frag in (
            "orders.payment_status",
            "orders.fulfillment_status",
            "orders.created_at >=",
            "orders.created_at <",
            "orders.total >=",
            "orders.total <=",
            "shipping_full_name",
            "profiles.email",
        ):
            assert frag in sql, frag


class TestStatusLiteral:
    def test_active_is_inlined_for_partial_index_matching(self):
        c = _filter_clauses(ProductFilterSpec(status="active"))["status"]
        assert str(c.compile(dialect=postgresql.dialect())) == (
            "products.status = 'active'"
        )

    def test_other_statuses_stay_bound(self):
        c = _filter_clauses(ProductFilterSpec(status="draft' OR 1=1 --"))["status"]
        sql = str(c.compile(dialect=postgresql.dialect()))
        assert "%(status_1)s" in sql and "OR 1=1" not in sql


class TestFacetCategoryRollup:
    async def test_inactive_child_counts_toward_active_parent(self):
        from unittest.mock import patch

        from app.modules.catalog.service import CatalogService

        parent, child, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

        def cat(cid, parent_id, active, slug):
            m = MagicMock()
            m.id, m.parent_id, m.is_active, m.slug, m.name = (
                cid,
                parent_id,
                active,
                slug,
                slug.title(),
            )
            return m

        tree = [
            cat(parent, None, True, "necklaces"),
            cat(child, parent, False, "chokers"),  # inactive sub-category
            cat(other, None, True, "rings"),
        ]
        raw = {
            "total": 5,
            "category_counts": {child: 3, parent: 2},
            "genders": [],
            "metal_types": [],
            "purities": [],
            "price_min": 1.0,
            "price_max": 2.0,
            "ratings": [{"min_rating": 4, "count": 0}],
            "in_stock": 5,
            "on_sale": 0,
            "new_arrival": 0,
            "best_seller": 0,
            "has_sales": False,
        }
        with (
            patch(
                "app.modules.catalog.service._repo.get_facets",
                AsyncMock(return_value=raw),
            ),
            patch(
                "app.modules.categories.repository.CategoryRepository"
                ".list_all_not_deleted",
                AsyncMock(return_value=tree),
            ),
        ):
            facets = await CatalogService().get_facets(
                MagicMock(), ProductFilterSpec(status="active")
            )
        by_slug = {c.slug: c.count for c in facets.categories}
        # Parent includes its inactive child's 3 products (matches the
        # descendant-inclusive list filter); inactive / empty ones hidden.
        assert by_slug == {"necklaces": 5}
        assert facets.ratings == []  # zero-count buckets dropped


class TestPastLastPageTotal:
    """COUNT(*) OVER() returns no rows past the end; total must still be real."""

    async def test_products_fall_back_to_count_past_last_page(self):
        from app.modules.catalog.repository import ProductRepository

        empty = MagicMock()
        empty.unique.return_value.all.return_value = []
        count = MagicMock()
        count.scalar_one.return_value = 148
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[empty, count])
        items, total = await ProductRepository().list_paginated(
            db, status="active", page=99
        )
        assert (items, total) == ([], 148)

    async def test_first_page_empty_makes_a_single_query(self):
        from app.modules.catalog.repository import ProductRepository

        empty = MagicMock()
        empty.unique.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[empty])
        assert await ProductRepository().list_paginated(db, page=1) == ([], 0)
        assert db.execute.await_count == 1
