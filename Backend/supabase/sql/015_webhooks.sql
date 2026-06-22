-- ============================================================
-- 015_webhooks.sql — Inbound webhook event log
-- ============================================================

CREATE TABLE IF NOT EXISTS webhook_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider        VARCHAR(30) NOT NULL,     -- 'razorpay' | 'delivery_one'
    event_type      VARCHAR(100) NOT NULL,    -- e.g. 'payment.captured'
    event_id        VARCHAR(255),             -- provider-assigned event ID (for idempotency)
    payload         TEXT NOT NULL,            -- raw JSON body
    status          VARCHAR(20) NOT NULL DEFAULT 'received',
    -- received | processed | failed | ignored
    error_message   TEXT,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, event_id)               -- prevents double-processing
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_provider   ON webhook_events(provider);
CREATE INDEX IF NOT EXISTS idx_webhook_events_event_type ON webhook_events(event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_events_status     ON webhook_events(status);
CREATE INDEX IF NOT EXISTS idx_webhook_events_created_at ON webhook_events(created_at DESC);

ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
-- Only service role can write/read webhook events (no customer policies)
