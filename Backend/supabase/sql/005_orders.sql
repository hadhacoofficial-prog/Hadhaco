-- ============================================================
-- 005_orders.sql
-- ============================================================

-- ── Orders ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number        VARCHAR(20) NOT NULL UNIQUE,
    user_id             UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,

    -- Status
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | confirmed | processing | shipped | delivered | cancelled | refunded
    payment_status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | paid | failed | refunded | partially_refunded

    -- Address snapshots (denormalised — address may change after order)
    shipping_full_name  VARCHAR(255) NOT NULL,
    shipping_phone      VARCHAR(20),
    shipping_line1      VARCHAR(255) NOT NULL,
    shipping_line2      VARCHAR(255),
    shipping_city       VARCHAR(100) NOT NULL,
    shipping_state      VARCHAR(100) NOT NULL,
    shipping_postal     VARCHAR(20) NOT NULL,
    shipping_country    VARCHAR(2) NOT NULL DEFAULT 'IN',

    billing_full_name   VARCHAR(255),
    billing_phone       VARCHAR(20),
    billing_line1       VARCHAR(255),
    billing_line2       VARCHAR(255),
    billing_city        VARCHAR(100),
    billing_state       VARCHAR(100),
    billing_postal      VARCHAR(20),
    billing_country     VARCHAR(2) DEFAULT 'IN',

    -- Financials
    subtotal            NUMERIC(12, 2) NOT NULL,
    tax_amount          NUMERIC(12, 2) NOT NULL DEFAULT 0,
    shipping_charge     NUMERIC(12, 2) NOT NULL DEFAULT 0,
    discount            NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total               NUMERIC(12, 2) NOT NULL,

    -- Coupon
    coupon_code         VARCHAR(50),
    coupon_id           UUID REFERENCES coupons(id) ON DELETE SET NULL,

    -- Payment
    payment_method      VARCHAR(30),   -- 'razorpay' | 'cod'
    razorpay_order_id   VARCHAR(100),
    razorpay_payment_id VARCHAR(100),

    -- Shipping
    shipping_provider   VARCHAR(50),
    tracking_number     VARCHAR(100),
    estimated_delivery  DATE,

    -- Misc
    notes               TEXT,
    cancellation_reason TEXT,
    cancelled_at        TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT orders_status_check CHECK (
        status IN ('pending','confirmed','processing','shipped','delivered','cancelled','refunded')
    ),
    CONSTRAINT orders_payment_status_check CHECK (
        payment_status IN ('pending','paid','failed','refunded','partially_refunded')
    )
);

CREATE INDEX IF NOT EXISTS idx_orders_user_id        ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_order_number   ON orders(order_number);
CREATE INDEX IF NOT EXISTS idx_orders_status         ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_status ON orders(payment_status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at     ON orders(created_at DESC);

DROP TRIGGER IF EXISTS set_orders_updated_at ON orders;
CREATE TRIGGER set_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Order Items ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS order_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id      UUID REFERENCES products(id) ON DELETE SET NULL,
    variant_id      UUID REFERENCES product_variants(id) ON DELETE SET NULL,

    -- Snapshot fields (product data at time of purchase)
    product_name    VARCHAR(255) NOT NULL,
    product_sku     VARCHAR(100) NOT NULL,
    variant_name    VARCHAR(255),
    unit_price      NUMERIC(12, 2) NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    tax_rate        NUMERIC(5, 2) NOT NULL DEFAULT 3.0,
    tax_amount      NUMERIC(12, 2) NOT NULL DEFAULT 0,
    line_total      NUMERIC(12, 2) NOT NULL,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id   ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);

-- ── RLS ───────────────────────────────────────────────────────────────────────

ALTER TABLE orders      ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;

-- Customers see only their own orders
DROP POLICY IF EXISTS "orders_owner_read" ON orders;
CREATE POLICY "orders_owner_read" ON orders FOR SELECT
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS "order_items_owner_read" ON order_items;
CREATE POLICY "order_items_owner_read" ON order_items FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM orders
            WHERE orders.id = order_items.order_id
            AND orders.user_id = auth.uid()
        )
    );

-- Admins can read all orders
DROP POLICY IF EXISTS "orders_admin_read" ON orders;
CREATE POLICY "orders_admin_read" ON orders FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
            AND profiles.role IN ('admin', 'super_admin')
        )
    );
