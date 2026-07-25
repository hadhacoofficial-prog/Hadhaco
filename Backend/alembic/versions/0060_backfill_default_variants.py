"""Backfill synthetic default variants for zero-variant products.

Part of the variant-first inventory migration. Every purchasable item must be
a ProductVariant going forward (a jewellery ring's Size 8/9/10 are each their
own variant with independent stock) — but 148 of this catalog's 154 products
predate that convention and carry their stock directly on the `products` row
instead. This migration gives each of them a synthetic "Default" variant that
inherits the product's current stock_quantity/reserved_quantity/sold_quantity,
so every product has >=1 variant and downstream code (cart, reservations,
search, the new admin inventory UI) can be written against ProductVariant
uniformly without a "does this product have variants?" branch everywhere.

This is Phase 1 of the migration and is purely additive (INSERT only) — it
does not touch the Product-level stock columns, which remain in place as a
safety net until a later, separately-approved migration drops them after a
production soak period.

sku collision note: products.sku and product_variants.sku are separate
uniqueness domains today (confirmed zero overlap on the live dev DB), so
reusing the product's own sku as the default variant's sku is safe. The
ON CONFLICT + suffixed second pass below is defensive only, for any product
whose sku happens to already be taken by a variant sku by the time this runs.

Also backfills cart_items.variant_id for any existing NULL rows, resolving to
the same "earliest active variant by sort_order/created_at" rule that
CartService._resolve_default_variant_id uses at the application layer — this
keeps pre-existing cart rows consistent with the variant-scoped reservation
and stock-lock code paths introduced alongside this migration, instead of
leaving them pointed at the (soon-to-be-vestigial) product-level columns.

Revision ID: 0060_backfill_default_variants
Revises: 0059_runtime_validated_index_cleanup
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0060_backfill_default_variants"
down_revision: str | None = "0059_runtime_validated_index_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Pass 1: reuse the product's own sku verbatim ────────────────────────
    op.execute("""
        INSERT INTO product_variants (
            id, product_id, sku, name, price_adjustment,
            stock_quantity, reserved_quantity, sold_quantity,
            weight_grams, is_active, sort_order, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            p.id,
            p.sku,
            'Default',
            0,
            p.stock_quantity,
            p.reserved_quantity,
            p.sold_quantity,
            p.weight_grams,
            (p.deleted_at IS NULL),
            0,
            p.created_at,
            now()
        FROM products p
        WHERE NOT EXISTS (
            SELECT 1 FROM product_variants v WHERE v.product_id = p.id
        )
        ON CONFLICT (sku) DO NOTHING
    """)

    # ── Pass 2: defensive retry with a suffixed sku for any collisions ──────
    op.execute("""
        INSERT INTO product_variants (
            id, product_id, sku, name, price_adjustment,
            stock_quantity, reserved_quantity, sold_quantity,
            weight_grams, is_active, sort_order, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            p.id,
            p.sku || '-DEFAULT',
            'Default',
            0,
            p.stock_quantity,
            p.reserved_quantity,
            p.sold_quantity,
            p.weight_grams,
            (p.deleted_at IS NULL),
            0,
            p.created_at,
            now()
        FROM products p
        WHERE NOT EXISTS (
            SELECT 1 FROM product_variants v WHERE v.product_id = p.id
        )
        ON CONFLICT (sku) DO NOTHING
    """)

    # ── Verification: fail loudly rather than silently leaving a gap ───────
    op.execute("""
        DO $$
        DECLARE
            orphan_count INT;
        BEGIN
            SELECT COUNT(*) INTO orphan_count
            FROM products p
            WHERE p.deleted_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM product_variants v WHERE v.product_id = p.id
              );
            IF orphan_count > 0 THEN
                RAISE EXCEPTION
                    'Backfill incomplete: % non-deleted products still have zero variants',
                    orphan_count;
            END IF;
        END $$;
    """)

    # ── Cart backfill: resolve NULL variant_id on existing cart rows ───────
    # Postgres UPDATE ... FROM cannot LATERAL-correlate against the update
    # target, so pre-aggregate one default variant per product_id first via
    # DISTINCT ON, then join that back on product_id.
    op.execute("""
        UPDATE cart_items ci
        SET variant_id = d.variant_id
        FROM (
            SELECT DISTINCT ON (v.product_id)
                v.product_id, v.id AS variant_id
            FROM product_variants v
            WHERE v.is_active = true
            ORDER BY v.product_id, v.sort_order ASC, v.created_at ASC
        ) d
        WHERE ci.variant_id IS NULL
          AND d.product_id = ci.product_id
    """)


def downgrade() -> None:
    # Un-resolve cart rows pointing at a variant this migration created,
    # before deleting those variants, to avoid FK violations/orphaned rows.
    op.execute("""
        UPDATE cart_items ci
        SET variant_id = NULL
        FROM product_variants v, products p
        WHERE ci.variant_id = v.id
          AND v.product_id = p.id
          AND v.name = 'Default'
          AND v.sort_order = 0
          AND v.price_adjustment = 0
          AND (v.sku = p.sku OR v.sku = p.sku || '-DEFAULT')
    """)

    # Delete only the variants this migration could have created — scoped by
    # the same shape (name/sort_order/price_adjustment/sku pattern) so a
    # legitimately hand-authored variant sharing the parent's sku isn't
    # destroyed.
    op.execute("""
        DELETE FROM product_variants v
        USING products p
        WHERE v.product_id = p.id
          AND v.name = 'Default'
          AND v.sort_order = 0
          AND v.price_adjustment = 0
          AND (v.sku = p.sku OR v.sku = p.sku || '-DEFAULT')
    """)
