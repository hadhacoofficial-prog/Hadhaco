-- ============================================================
-- feature_flag_complimentary_gift.sql
--
-- Seeds the `feature_flags` row that gates the complimentary-gift feature.
-- app/modules/orders/service.py:1011-1014 (set_complimentary_gift) checks
-- SettingsService.is_feature_enabled(db, "complimentary_gift_enabled")
-- before letting a customer pick a gift on a paid order >= ₹2000
-- (order.total < 2000 is rejected regardless of this flag - see
-- orders/service.py:1020-1021). Right now this flag row doesn't exist at
-- all, and is_feature_enabled() returns False for a missing key
-- (app/modules/settings/service.py:46-48), so the feature is hard-off
-- until this row exists.
--
-- Once seeded, toggle it from the admin panel via:
--   PUT /admin/settings/flags/complimentary_gift_enabled  {"value": true|false}
-- (app/modules/settings/router.py:51-65) - that endpoint upserts this same
-- row and busts its Redis cache (`flag:v1:complimentary_gift_enabled`), so
-- you do not need to re-run this script to flip it after this seed exists.
--
-- Idempotent: ON CONFLICT (key) DO NOTHING - if an admin has already
-- toggled this flag (via the endpoint above) after some earlier partial
-- setup, re-running this script must not silently override their choice.
-- Change the `value` below to FALSE if you want it seeded OFF instead.
-- ============================================================

BEGIN;

INSERT INTO feature_flags (key, value, description, updated_at)
VALUES (
    'complimentary_gift_enabled',
    TRUE,
    'Lets customers pick a complimentary gift on paid orders >= Rs 2000 (see app/modules/orders/service.py set_complimentary_gift).',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

-- ── Validation ───────────────────────────────────────────────────────────
DO $$
DECLARE
    flag_value BOOLEAN;
BEGIN
    SELECT value INTO flag_value FROM feature_flags WHERE key = 'complimentary_gift_enabled';
    IF flag_value IS NULL THEN
        RAISE EXCEPTION 'complimentary_gift_enabled flag missing after seed attempt';
    END IF;
    RAISE NOTICE 'complimentary_gift_enabled = %', flag_value;
END $$;

COMMIT;
