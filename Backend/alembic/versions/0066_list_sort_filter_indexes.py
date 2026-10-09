"""Indexes backing the site-wide sorting & filtering work.

Storefront product listings always filter ``deleted_at IS NULL AND
status = 'active'`` and then ORDER BY one of the shopper-facing sort keys,
paginating with OFFSET/LIMIT and an ``id`` tie-breaker. Partial btree
indexes over exactly that predicate let Postgres walk the index in sort
order and stop after one page instead of sorting the whole catalogue:

  - idx_products_live_created_at     -> Newest (default listing order)
  - idx_products_live_base_price     -> Price low/high
  - idx_products_live_sold_quantity  -> Best selling
  - idx_products_live_average_rating -> Top rated
  - idx_products_live_gender         -> gender filter (every nav link)

Admin tables:
  - idx_orders_total                 -> sort orders by value
  - idx_orders_shipping_name_trgm    -> order search by customer name
  - idx_reviews_product_created_at   -> PDP review list (filter + newest)
  - idx_reviews_created_at           -> admin review list default order
  - idx_profiles_created_at          -> customer list default order / joined range
  - idx_coupons_created_at           -> coupon list default order

pg_trgm is already installed (idx_products_name_trgm, migration 0063).
All CONCURRENTLY + IF NOT EXISTS — additive, non-blocking, re-runnable.

Revision ID: 0066_list_sort_filter_indexes
Revises: 0065_worker_sweep_indexes
Create Date: 2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0066_list_sort_filter_indexes"
down_revision: str | None = "0065_worker_sweep_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = "WHERE deleted_at IS NULL AND status = 'active'"

_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "idx_products_live_created_at",
        f"ON products (created_at DESC, id) {_LIVE}",
    ),
    ("idx_products_live_base_price", f"ON products (base_price, id) {_LIVE}"),
    (
        "idx_products_live_sold_quantity",
        f"ON products (sold_quantity DESC, id) {_LIVE}",
    ),
    (
        "idx_products_live_average_rating",
        f"ON products (average_rating DESC NULLS LAST, id) {_LIVE}",
    ),
    ("idx_products_live_gender", f"ON products (gender) {_LIVE}"),
    ("idx_orders_total", "ON orders (total)"),
    (
        "idx_orders_shipping_name_trgm",
        "ON orders USING gin (shipping_full_name gin_trgm_ops)",
    ),
    (
        "idx_reviews_product_created_at",
        "ON reviews (product_id, created_at DESC) WHERE deleted_at IS NULL",
    ),
    ("idx_reviews_created_at", "ON reviews (created_at DESC)"),
    ("idx_profiles_created_at", "ON profiles (created_at DESC)"),
    ("idx_coupons_created_at", "ON coupons (created_at DESC)"),
)


def upgrade() -> None:
    for name, definition in _INDEXES:
        with op.get_context().autocommit_block():
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} {definition}")


def downgrade() -> None:
    for name, _ in reversed(_INDEXES):
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
