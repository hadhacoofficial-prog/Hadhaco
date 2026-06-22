-- ============================================================
-- setup.sql — Master script
-- Sources all SQL files in dependency order. Running this once
-- builds the complete database from scratch; re-running is safe
-- (all files are idempotent: IF NOT EXISTS / OR REPLACE /
-- DROP ... IF EXISTS guards).
--
-- Usage (psql, from this directory):
--   psql $DATABASE_URL -f setup.sql
-- ============================================================

\i 000_extensions.sql
\i 001_profiles.sql
\i 002_catalog.sql
\i 003_inventory.sql
\i 004_addresses_wishlist_cart.sql
\i 009_coupons.sql
\i 005_orders.sql
\i 006_payments.sql
\i 007_shipping.sql
\i 008_reviews.sql
\i 024_returns.sql
\i 010_cms.sql
\i 011_analytics.sql
\i 012_notifications.sql
\i 013_audit_logs.sql
\i 015_webhooks.sql
\i 016_fraud.sql
\i 017_support.sql
\i 018_feature_flags.sql
\i 019_views.sql
\i 020_indexes.sql
\i 021_rls.sql
\i 022_triggers.sql
\i 023_seed_data.sql
