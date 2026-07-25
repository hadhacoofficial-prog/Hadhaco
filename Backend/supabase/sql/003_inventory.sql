-- ============================================================
-- 003_inventory.sql — Inventory movements ledger
-- ============================================================

-- ── Types ─────────────────────────────────────────────────────────────────────

DO $$ BEGIN
    CREATE TYPE inventory_movement_type AS ENUM (
        'purchase',
        'sale',
        'return',
        'adjustment',
        'damage',
        'transfer',
        'correction'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;


-- ── Tables ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS inventory_movements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id          UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_id          UUID REFERENCES product_variants(id) ON DELETE SET NULL,
    movement_type       inventory_movement_type NOT NULL,
    delta               INTEGER NOT NULL,            -- positive = add, negative = remove
    quantity_before     INTEGER NOT NULL,
    quantity_after      INTEGER NOT NULL,
    reference_type      VARCHAR(50),                 -- 'order', 'return', 'manual_adjustment', etc.
    reference_id        VARCHAR(36),                 -- ID of the referenced entity
    notes               TEXT,
    created_by          UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_inventory_movements_product_id
    ON inventory_movements(product_id);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_variant_id
    ON inventory_movements(variant_id);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_movement_type
    ON inventory_movements(movement_type);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_reference
    ON inventory_movements(reference_type, reference_id);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_created_at
    ON inventory_movements(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_created_by
    ON inventory_movements(created_by);


-- ── RLS ───────────────────────────────────────────────────────────────────────

ALTER TABLE inventory_movements ENABLE ROW LEVEL SECURITY;

-- Admins can read all movements
DROP POLICY IF EXISTS "inventory_movements_admin_read" ON inventory_movements;
CREATE POLICY "inventory_movements_admin_read" ON inventory_movements FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
            AND profiles.role IN ('admin', 'super_admin')
            AND profiles.is_active = true
        )
    );

-- Service role bypasses RLS (FastAPI backend)


-- ── Low-stock view ────────────────────────────────────────────────────────────
-- NOTE: this file is a hand-maintained reference snapshot, not applied via
-- Alembic. The live schema is governed by Backend/alembic/versions/ — this
-- view was rewritten as variant-level + available_stock-aware in
-- 0062_variant_aware_low_stock_view.py (2026-07-25). Keep this in sync so it
-- doesn't silently describe a schema that no longer exists.

CREATE OR REPLACE VIEW low_stock_products AS
    SELECT
        v.id AS variant_id,
        v.product_id,
        v.sku,
        v.name AS variant_name,
        p.name AS product_name,
        GREATEST(v.stock_quantity - v.reserved_quantity - v.sold_quantity, 0)
            AS available_stock,
        v.stock_quantity,
        p.low_stock_threshold,
        p.status,
        p.category_id
    FROM product_variants v
    JOIN products p ON p.id = v.product_id
    WHERE
        p.deleted_at IS NULL
        AND p.track_inventory = true
        AND v.is_active = true
        AND GREATEST(v.stock_quantity - v.reserved_quantity - v.sold_quantity, 0)
            <= p.low_stock_threshold;

