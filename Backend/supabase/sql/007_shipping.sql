-- ============================================================
-- 007_shipping.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS shipments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID NOT NULL UNIQUE REFERENCES orders(id) ON DELETE RESTRICT,
    provider            VARCHAR(50) NOT NULL DEFAULT 'delivery_one',
    provider_shipment_id VARCHAR(100),     -- Delivery One internal ID
    awb_number          VARCHAR(100),      -- Air Waybill / tracking number
    label_url           TEXT,              -- R2 URL for shipping label PDF
    label_r2_key        VARCHAR(512),
    status              VARCHAR(30) NOT NULL DEFAULT 'pending',
    -- pending | created | picked_up | in_transit | out_for_delivery | delivered | cancelled | failed
    weight_grams        INTEGER,
    length_cm           NUMERIC(8, 2),
    width_cm            NUMERIC(8, 2),
    height_cm           NUMERIC(8, 2),
    estimated_delivery  DATE,
    pickup_scheduled_at TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ,
    cancelled_at        TIMESTAMPTZ,
    cancel_reason       TEXT,
    raw_response        TEXT,              -- last API response (debug)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT shipments_status_check CHECK (
        status IN ('pending','created','picked_up','in_transit','out_for_delivery','delivered','cancelled','failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_shipments_order_id   ON shipments(order_id);
CREATE INDEX IF NOT EXISTS idx_shipments_awb_number ON shipments(awb_number);
CREATE INDEX IF NOT EXISTS idx_shipments_status     ON shipments(status);

DROP TRIGGER IF EXISTS set_shipments_updated_at ON shipments;
CREATE TRIGGER set_shipments_updated_at
    BEFORE UPDATE ON shipments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Shipment tracking events ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS shipment_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipment_id     UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    status          VARCHAR(50) NOT NULL,
    description     TEXT,
    location        VARCHAR(255),
    occurred_at     TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shipment_events_shipment_id ON shipment_events(shipment_id);
CREATE INDEX IF NOT EXISTS idx_shipment_events_occurred_at ON shipment_events(occurred_at DESC);

-- ── RLS ───────────────────────────────────────────────────────────────────────

ALTER TABLE shipments       ENABLE ROW LEVEL SECURITY;
ALTER TABLE shipment_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "shipments_owner_read" ON shipments;
CREATE POLICY "shipments_owner_read" ON shipments FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM orders
            WHERE orders.id = shipments.order_id
            AND orders.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "shipment_events_owner_read" ON shipment_events;
CREATE POLICY "shipment_events_owner_read" ON shipment_events FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM shipments s
            JOIN orders o ON o.id = s.order_id
            WHERE s.id = shipment_events.shipment_id
            AND o.user_id = auth.uid()
        )
    );
