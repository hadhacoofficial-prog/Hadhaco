-- ============================================================
-- 021_rls.sql  — additional RLS policies (modules not yet covered)
-- ============================================================

-- Analytics events: public insert (anonymous tracking), no reads via API
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "analytics_insert_any" ON analytics_events;
CREATE POLICY "analytics_insert_any" ON analytics_events FOR INSERT WITH CHECK (TRUE);

-- Audit logs: admin read only
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "audit_admin_read" ON audit_logs;
CREATE POLICY "audit_admin_read" ON audit_logs FOR SELECT
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));

-- Fraud signals: admin only
ALTER TABLE fraud_signals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "fraud_admin_all" ON fraud_signals;
CREATE POLICY "fraud_admin_all" ON fraud_signals FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));

-- Feature flags: admin write, public read
ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "flags_public_read" ON feature_flags;
CREATE POLICY "flags_public_read" ON feature_flags FOR SELECT USING (TRUE);
DROP POLICY IF EXISTS "flags_admin_write" ON feature_flags;
CREATE POLICY "flags_admin_write" ON feature_flags FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));

-- Notification logs: own reads
ALTER TABLE notification_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "notif_logs_own" ON notification_logs;
CREATE POLICY "notif_logs_own" ON notification_logs FOR SELECT USING (user_id = auth.uid());
DROP POLICY IF EXISTS "notif_logs_admin" ON notification_logs;
CREATE POLICY "notif_logs_admin" ON notification_logs FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));

-- Returns
ALTER TABLE returns ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "returns_own" ON returns;
CREATE POLICY "returns_own" ON returns FOR ALL
    USING (customer_id = auth.uid()) WITH CHECK (customer_id = auth.uid());
DROP POLICY IF EXISTS "returns_admin" ON returns;
CREATE POLICY "returns_admin" ON returns FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));

-- CMS: public read, admin write
ALTER TABLE banners          ENABLE ROW LEVEL SECURITY;
ALTER TABLE landing_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE cms_pages        ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings     ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cms_public_read" ON banners;
CREATE POLICY "cms_public_read" ON banners          FOR SELECT USING (TRUE);
DROP POLICY IF EXISTS "cms_admin_write" ON banners;
CREATE POLICY "cms_admin_write" ON banners          FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));
DROP POLICY IF EXISTS "ls_public_read" ON landing_sections;
CREATE POLICY "ls_public_read" ON landing_sections FOR SELECT USING (TRUE);
DROP POLICY IF EXISTS "ls_admin_write" ON landing_sections;
CREATE POLICY "ls_admin_write" ON landing_sections FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));
DROP POLICY IF EXISTS "pages_public_read" ON cms_pages;
CREATE POLICY "pages_public_read" ON cms_pages         FOR SELECT USING (is_published = TRUE);
DROP POLICY IF EXISTS "pages_admin_all" ON cms_pages;
CREATE POLICY "pages_admin_all" ON cms_pages         FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));
DROP POLICY IF EXISTS "settings_public_read" ON app_settings;
CREATE POLICY "settings_public_read" ON app_settings   FOR SELECT USING (TRUE);
DROP POLICY IF EXISTS "settings_admin_write" ON app_settings;
CREATE POLICY "settings_admin_write" ON app_settings   FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin','super_admin')));
