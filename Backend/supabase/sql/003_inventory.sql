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

CREATE OR REPLACE VIEW low_stock_products AS
    SELECT
        p.id,
        p.sku,
        p.name,
        p.stock_quantity,
        p.low_stock_threshold,
        p.status,
        p.category_id
    FROM products p
    WHERE
        p.deleted_at IS NULL
        AND p.track_inventory = true
        AND p.stock_quantity <= p.low_stock_threshold;

