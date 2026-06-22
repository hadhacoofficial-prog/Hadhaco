-- ============================================================
-- 022_triggers.sql  — domain triggers
-- ============================================================

-- Auto-update updated_at (also defined early in 000_extensions for table files)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- Apply to tables that carry updated_at but don't have a trigger yet
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'products', 'categories', 'collections',
        'orders', 'profiles', 'user_addresses',
        'coupons', 'returns', 'seo_pages', 'seo_redirects'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.triggers
            WHERE trigger_name = 'set_' || tbl || '_updated_at'
              AND event_object_table = tbl
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER set_%I_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
                tbl, tbl
            );
        END IF;
    END LOOP;
END;
$$;

-- NOTE: stock decrement/restore is intentionally handled in the service layer
-- (app/modules/inventory + orders service) with a movements ledger and
-- SELECT ... FOR UPDATE row locks. No DB trigger touches stock_quantity, so
-- the application remains the single writer for stock.

-- Auto-partition creator for analytics_events (called monthly by worker)
CREATE OR REPLACE FUNCTION create_analytics_partition(target_month DATE)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    partition_name TEXT;
    start_date     DATE;
    end_date       DATE;
BEGIN
    start_date     := DATE_TRUNC('month', target_month);
    end_date       := start_date + INTERVAL '1 month';
    partition_name := 'analytics_events_' || TO_CHAR(start_date, 'YYYY_MM');
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = partition_name) THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF analytics_events FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_date, end_date
        );
    END IF;
END;
$$;

-- Auto-partition creator for audit_logs (called monthly by worker)
CREATE OR REPLACE FUNCTION create_audit_partition(target_month DATE)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    partition_name TEXT;
    start_date     DATE;
    end_date       DATE;
BEGIN
    start_date     := DATE_TRUNC('month', target_month);
    end_date       := start_date + INTERVAL '1 month';
    partition_name := 'audit_logs_' || TO_CHAR(start_date, 'YYYY_MM');
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = partition_name) THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF audit_logs FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_date, end_date
        );
    END IF;
END;
$$;
