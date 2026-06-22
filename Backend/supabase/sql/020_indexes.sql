-- ============================================================
-- 020_indexes.sql — performance indexes not already in table SQL
-- ============================================================

-- Products
CREATE INDEX IF NOT EXISTS idx_products_status_featured ON products(status, is_featured) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_products_compare_price   ON products(compare_at_price) WHERE compare_at_price IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_products_low_stock       ON products(stock_quantity) WHERE track_inventory = TRUE AND deleted_at IS NULL;

-- Orders
CREATE INDEX IF NOT EXISTS idx_orders_user_status    ON orders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_created_status ON orders(created_at DESC, status);

-- Cart (guest sessions)
CREATE INDEX IF NOT EXISTS idx_carts_session ON carts(session_id) WHERE session_id IS NOT NULL;

-- Coupons
CREATE INDEX IF NOT EXISTS idx_coupon_usages_user ON coupon_usages(user_id);

-- Analytics
CREATE INDEX IF NOT EXISTS idx_analytics_session ON analytics_events(session_id);

-- Notifications
CREATE INDEX IF NOT EXISTS idx_notif_logs_pending ON notification_logs(status) WHERE status IN ('pending','retrying');
CREATE INDEX IF NOT EXISTS idx_notif_logs_user    ON notification_logs(user_id);

-- Support
CREATE INDEX IF NOT EXISTS idx_support_assigned ON support_tickets(assigned_to) WHERE assigned_to IS NOT NULL;

-- Reviews
CREATE INDEX IF NOT EXISTS idx_reviews_product_approved ON reviews(product_id) WHERE is_approved = TRUE AND deleted_at IS NULL;
