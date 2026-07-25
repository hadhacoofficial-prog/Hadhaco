"""Rewrite low_stock_products as a variant-level, available_stock-aware view.

The view previously lived only in the untracked reference file
supabase/sql/003_inventory.sql (applied out-of-band, never through Alembic)
and had two bugs consistent with the rest of the pre-variant-first codebase:

  1. Product-only — a variant-bearing product whose parent row's own
     stock_quantity happened to look fine would never surface here even if
     its variants were critically low (or vice versa).
  2. Compared raw stock_quantity to threshold instead of available_stock
     (stock - reserved - sold) — a product that's nearly sold out but whose
     warehouse total hasn't been restocked never showed as low-stock.

This migration brings the view under Alembic for the first time and
replaces it with a variant-level definition using the same
GREATEST(stock - reserved - sold, 0) formula as compute_available_stock()
in inventory/status.py.

Because the live view's columns are being renamed/reordered (id ->
variant_id, name -> variant_name, + new product_id/product_name/
available_stock columns), CREATE OR REPLACE VIEW cannot be used here —
Postgres only allows CREATE OR REPLACE to append trailing columns, not
rename existing ones. Must DROP then CREATE.

Revision ID: 0062_variant_aware_low_stock_view
Revises: 0061_extend_inventory_transaction_audit
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0062_variant_aware_low_stock_view"
down_revision: str | None = "0061_extend_inventory_transaction_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS low_stock_products")
    op.execute("""
        CREATE VIEW low_stock_products AS
        SELECT
            v.id AS variant_id,
            v.product_id,
            v.sku,
            v.name AS variant_name,
            p.name AS product_name,
            GREATEST(v.stock_quantity - v.reserved_quantity - v.sold_quantity, 0)
                AS available_stock,  -- mirrors compute_available_stock()
            v.stock_quantity,
            p.low_stock_threshold,
            p.status,
            p.category_id
        FROM product_variants v
        JOIN products p ON p.id = v.product_id
        WHERE p.deleted_at IS NULL
          AND p.track_inventory = true
          AND v.is_active = true
          AND GREATEST(v.stock_quantity - v.reserved_quantity - v.sold_quantity, 0)
              <= p.low_stock_threshold
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS low_stock_products")
    op.execute("""
        CREATE VIEW low_stock_products AS
        SELECT
            p.id,
            p.sku,
            p.name,
            p.stock_quantity,
            p.low_stock_threshold,
            p.status,
            p.category_id
        FROM products p
        WHERE p.deleted_at IS NULL
          AND p.track_inventory = true
          AND p.stock_quantity <= p.low_stock_threshold
    """)
