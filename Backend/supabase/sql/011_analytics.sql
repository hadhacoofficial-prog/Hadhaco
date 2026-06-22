-- ============================================================
-- 011_analytics.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS analytics_events (
    id          UUID DEFAULT gen_random_uuid(),
    event_type  TEXT NOT NULL CHECK (event_type IN (
                    'product_view','add_to_cart','remove_from_cart',
                    'checkout_started','purchase_completed',
                    'search','category_view','collection_view',
                    'wishlist_add','coupon_applied'
                )),
    user_id     UUID REFERENCES profiles(id),
    session_id  TEXT,
    product_id  UUID REFERENCES products(id),
    category_id UUID REFERENCES categories(id),
    order_id    UUID,
    metadata    JSONB DEFAULT '{}',
    ip_address  INET,
    user_agent  TEXT,
    referrer    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Current + next month partitions (future months added by worker/migration)
CREATE TABLE IF NOT EXISTS analytics_events_2026_06 PARTITION OF analytics_events
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE IF NOT EXISTS analytics_events_2026_07 PARTITION OF analytics_events
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE IF NOT EXISTS analytics_events_2026_08 PARTITION OF analytics_events
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE TABLE IF NOT EXISTS analytics_events_2026_09 PARTITION OF analytics_events
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE TABLE IF NOT EXISTS analytics_events_2026_10 PARTITION OF analytics_events
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE IF NOT EXISTS analytics_events_2026_11 PARTITION OF analytics_events
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE IF NOT EXISTS analytics_events_2026_12 PARTITION OF analytics_events
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS analytics_events_2027_01 PARTITION OF analytics_events
    FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');

CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_user_id    ON analytics_events(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_product_id ON analytics_events(product_id);
CREATE INDEX IF NOT EXISTS idx_analytics_created    ON analytics_events(created_at DESC);
