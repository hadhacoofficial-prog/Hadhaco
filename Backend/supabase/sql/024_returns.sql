-- ============================================================
-- 024_returns.sql — Returns / RMA
-- Tables: returns, return_items
-- Schema matches app/modules/returns/models.py
-- ============================================================

CREATE TABLE IF NOT EXISTS public.returns (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID NOT NULL REFERENCES public.orders(id),
    customer_id         UUID NOT NULL REFERENCES public.profiles(id),
    reason              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'requested'
                            CHECK (status IN ('requested','approved','rejected','pickup_scheduled','received','refunded','closed')),
    admin_notes         TEXT,
    reviewed_by         UUID,
    reviewed_at         TIMESTAMPTZ,
    pickup_scheduled_at TIMESTAMPTZ,
    received_at         TIMESTAMPTZ,
    refund_id           UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_returns_order_id    ON public.returns(order_id);
CREATE INDEX IF NOT EXISTS idx_returns_customer_id ON public.returns(customer_id);
CREATE INDEX IF NOT EXISTS idx_returns_status      ON public.returns(status);
CREATE INDEX IF NOT EXISTS idx_returns_created_at  ON public.returns(created_at DESC);

CREATE TABLE IF NOT EXISTS public.return_items (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    return_id     UUID NOT NULL REFERENCES public.returns(id) ON DELETE CASCADE,
    order_item_id UUID NOT NULL REFERENCES public.order_items(id),
    quantity      INTEGER NOT NULL,
    reason        TEXT,
    condition     TEXT,
    received_qty  INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_return_items_qty CHECK (quantity > 0)
);

CREATE INDEX IF NOT EXISTS idx_return_items_return_id     ON public.return_items(return_id);
CREATE INDEX IF NOT EXISTS idx_return_items_order_item_id ON public.return_items(order_item_id);

-- updated_at trigger
DROP TRIGGER IF EXISTS trg_returns_updated_at ON public.returns;
CREATE TRIGGER trg_returns_updated_at
    BEFORE UPDATE ON public.returns
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── RLS ───────────────────────────────────────────────────────────────────────
ALTER TABLE public.returns      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.return_items ENABLE ROW LEVEL SECURITY;

-- Customers see their own returns
DROP POLICY IF EXISTS "returns_owner_read" ON public.returns;
CREATE POLICY "returns_owner_read"
    ON public.returns FOR SELECT
    USING (customer_id = auth.uid());

DROP POLICY IF EXISTS "return_items_owner_read" ON public.return_items;
CREATE POLICY "return_items_owner_read"
    ON public.return_items FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.returns r
            WHERE r.id = return_items.return_id
            AND r.customer_id = auth.uid()
        )
    );

-- Admins read everything
DROP POLICY IF EXISTS "returns_admin_read" ON public.returns;
CREATE POLICY "returns_admin_read"
    ON public.returns FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid()
            AND profiles.role IN ('admin', 'super_admin')
            AND profiles.is_active = TRUE
        )
    );
