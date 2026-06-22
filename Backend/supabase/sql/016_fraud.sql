-- ============================================================
-- 016_fraud.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS fraud_signals (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES profiles(id),
    ip_address  INET,
    signal_type TEXT NOT NULL CHECK (signal_type IN (
                    'duplicate_order','velocity_order','multiple_payment_failures',
                    'suspicious_login','account_lockout','unusual_refund_pattern',
                    'coupon_abuse','bot_detection'
                )),
    severity    TEXT NOT NULL DEFAULT 'medium'
                    CHECK (severity IN ('low','medium','high','critical')),
    description TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by UUID REFERENCES profiles(id),
    resolved_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fraud_signals_user_id  ON fraud_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_fraud_signals_ip       ON fraud_signals(ip_address);
CREATE INDEX IF NOT EXISTS idx_fraud_signals_type     ON fraud_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_fraud_signals_resolved ON fraud_signals(is_resolved) WHERE is_resolved = FALSE;
