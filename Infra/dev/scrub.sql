-- Scrub a restored production backup for local development.
-- Runs once, in one transaction, right after the restore (restore-from-s3.sh).
-- Removes or replaces personal data and secrets; keeps the shape and volume of
-- the data (orders, catalog, reviews...) so the app behaves realistically.
BEGIN;

-- Logs and free-text that carry emails, IPs, user agents or message bodies.
TRUNCATE
  analytics_events, audit_logs, notification_logs, seo_404_log, fraud_signals,
  contact_enquiries, search_history, webhook_events,
  support_messages, support_tickets;

-- Live logins, one-time links, Google links and admin 2FA secrets (so no
-- authenticator app is needed locally).
TRUNCATE auth_sessions, auth_tokens, oauth_identities, admin_sessions, admin_2fa;

-- Stored provider secrets (the app falls back to Backend/.env values).
DELETE FROM notification_provider_settings;

-- Accounts: deterministic fake identities. Admins become adminN@hadha.test.
WITH n AS (
  SELECT id, role, row_number() OVER (ORDER BY created_at, id) AS rn FROM profiles
)
UPDATE profiles p
   SET email     = CASE WHEN n.role IN ('admin', 'super_admin')
                        THEN 'admin' || n.rn || '@hadha.test'
                        ELSE 'user'  || n.rn || '@example.test' END,
       full_name = CASE WHEN n.role IN ('admin', 'super_admin')
                        THEN 'Dev Admin ' || n.rn
                        ELSE 'Dev User '  || n.rn END,
       phone       = NULL,
       is_verified = true
  FROM n
 WHERE p.id = n.id;

-- One known password for every account (bcrypt, same format the app verifies).
INSERT INTO user_credentials (user_id, password_hash, email_verified_at, password_changed_at)
SELECT id, crypt('DevPass123!', gen_salt('bf', 10)), now(), now() FROM profiles
ON CONFLICT (user_id) DO UPDATE
   SET password_hash       = EXCLUDED.password_hash,
       email_verified_at   = now(),
       password_changed_at = now();

-- Addresses (saved and on orders). City and postal code are kept: they are
-- needed for shipping/tax logic and do not identify anyone on their own.
UPDATE user_addresses
   SET full_name = 'Dev User', phone = '9999999999', alternate_phone = NULL,
       line1 = 'Dev Street 1', line2 = NULL;

UPDATE orders
   SET billing_full_name  = 'Dev User', billing_phone  = '9999999999', billing_alternate_phone  = NULL,
       billing_line1      = 'Dev Street 1', billing_line2 = NULL,
       shipping_full_name = 'Dev User', shipping_phone = '9999999999', shipping_alternate_phone = NULL,
       shipping_line1     = 'Dev Street 1', shipping_line2 = NULL;

UPDATE reviews SET customer_name = 'Dev Customer';

-- Coupon allow-lists can name real customers.
UPDATE coupons SET allowed_emails = NULL, allowed_phone_numbers = NULL;

-- Marks the database as scrubbed. restore-from-s3.sh refuses to reuse a database
-- that has data but no marker (an interrupted restore would leave raw data).
CREATE TABLE _dev_scrubbed AS SELECT now() AS scrubbed_at;

COMMIT;
