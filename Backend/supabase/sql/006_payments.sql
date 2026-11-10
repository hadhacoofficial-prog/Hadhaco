-- ============================================================
-- 006_payments.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS payments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id                UUID NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    user_id                 UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,

    -- Razorpay identifiers
    razorpay_order_id       VARCHAR(100) NOT NULL,
    razorpay_payment_id     VARCHAR(100),
    razorpay_signature      VARCHAR(255),

    amount                  NUMERIC(12, 2) NOT NULL,   -- in INR
    currency                VARCHAR(3) NOT NULL DEFAULT 'INR',
    method                  VARCHAR(30),               -- upi | card | netbanking | wallet | cod
    status                  VARCHAR(20) NOT NULL DEFAULT 'created',
    -- created | authorized | captured | failed | refunded | partially_refunded

    failure_reason          TEXT,
    captured_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT payments_status_check CHECK (
        status IN ('created','authorized','captured','failed','refunded','partially_refunded')
    )
);

CREATE INDEX IF NOT EXISTS idx_payments_order_id            ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id             ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_razorpay_order_id   ON payments(razorpay_order_id);
CREATE INDEX IF NOT EXISTS idx_payments_razorpay_payment_id ON payments(razorpay_payment_id);
CREATE INDEX IF NOT EXISTS idx_payments_status              ON payments(status);

DROP TRIGGER IF EXISTS set_payments_updated_at ON payments;
CREATE TRIGGER set_payments_updated_at
    BEFORE UPDATE ON payments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Refunds ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS refunds (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id          UUID NOT NULL REFERENCES payments(id) ON DELETE RESTRICT,
    order_id            UUID NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    razorpay_refund_id  VARCHAR(100),
    amount              NUMERIC(12, 2) NOT NULL,
    reason              TEXT,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | processed | failed
    processed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_refunds_payment_id ON refunds(payment_id);
CREATE INDEX IF NOT EXISTS idx_refunds_order_id   ON refunds(order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_status     ON refunds(status);

DROP TRIGGER IF EXISTS set_refunds_updated_at ON refunds;
CREATE TRIGGER set_refunds_updated_at
    BEFORE UPDATE ON refunds
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Invoices ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS invoices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL UNIQUE REFERENCES orders(id) ON DELETE RESTRICT,
    invoice_number  VARCHAR(30) NOT NULL UNIQUE,
    pdf_url         TEXT,                       -- R2 public URL
    pdf_r2_key      VARCHAR(512),               -- R2 object key for deletion
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invoices_order_id       ON invoices(order_id);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices(invoice_number);

-- ── RLS ───────────────────────────────────────────────────────────────────────

ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE refunds  ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "payments_owner_read" ON payments;
CREATE POLICY "payments_owner_read" ON payments FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS "refunds_owner_read" ON refunds;
CREATE POLICY "refunds_owner_read" ON refunds FOR SELECT
    USING (
        EXISTS (SELECT 1 FROM payments WHERE payments.id = refunds.payment_id AND payments.user_id = auth.uid())
    );

DROP POLICY IF EXISTS "invoices_owner_read" ON invoices;
CREATE POLICY "invoices_owner_read" ON invoices FOR SELECT
    USING (
        EXISTS (SELECT 1 FROM orders WHERE orders.id = invoices.order_id AND orders.user_id = auth.uid())
    );
