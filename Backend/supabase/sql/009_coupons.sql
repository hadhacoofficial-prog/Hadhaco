-- ============================================================
-- 009_coupons.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS coupons (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                VARCHAR(50) NOT NULL UNIQUE,
    description         TEXT,
    coupon_type         VARCHAR(20) NOT NULL DEFAULT 'percentage',  -- 'percentage' | 'fixed_amount' | 'free_shipping'
    value               NUMERIC(12, 2) NOT NULL,                   -- % or INR amount
    min_order_amount    NUMERIC(12, 2) NOT NULL DEFAULT 0,
    max_discount        NUMERIC(12, 2),                            -- cap for percentage coupons
    usage_limit         INTEGER,                                    -- NULL = unlimited
    usage_count         INTEGER NOT NULL DEFAULT 0,
    per_user_limit      INTEGER NOT NULL DEFAULT 1,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT coupons_value_positive CHECK (value > 0),
    CONSTRAINT coupons_type_check CHECK (coupon_type IN ('percentage', 'fixed_amount', 'free_shipping')),
    CONSTRAINT coupons_percentage_max CHECK (coupon_type != 'percentage' OR value <= 100)
);

CREATE INDEX IF NOT EXISTS idx_coupons_code      ON coupons(code);
CREATE INDEX IF NOT EXISTS idx_coupons_is_active ON coupons(is_active);
CREATE INDEX IF NOT EXISTS idx_coupons_valid     ON coupons(valid_from, valid_until);

DROP TRIGGER IF EXISTS set_coupons_updated_at ON coupons;
CREATE TRIGGER set_coupons_updated_at
    BEFORE UPDATE ON coupons
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Coupon usages (one row per order that applied a coupon)
CREATE TABLE IF NOT EXISTS coupon_usages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coupon_id   UUID NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_id    UUID,                    -- filled in after order is created
    discount    NUMERIC(12, 2) NOT NULL,
    used_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (coupon_id, order_id)
);

CREATE INDEX IF NOT EXISTS idx_coupon_usages_coupon_id ON coupon_usages(coupon_id);
CREATE INDEX IF NOT EXISTS idx_coupon_usages_user_id   ON coupon_usages(user_id);
CREATE INDEX IF NOT EXISTS idx_coupon_usages_order_id  ON coupon_usages(order_id);

ALTER TABLE coupons       ENABLE ROW LEVEL SECURITY;
ALTER TABLE coupon_usages ENABLE ROW LEVEL SECURITY;

-- Customers can read active coupons (for public lookup by code)
DROP POLICY IF EXISTS "coupons_public_read" ON coupons;
CREATE POLICY "coupons_public_read" ON coupons FOR SELECT
    USING (is_active = true AND (valid_until IS NULL OR valid_until > now()));

DROP POLICY IF EXISTS "coupon_usages_owner_read" ON coupon_usages;
CREATE POLICY "coupon_usages_owner_read" ON coupon_usages FOR SELECT
    USING (user_id = auth.uid());
