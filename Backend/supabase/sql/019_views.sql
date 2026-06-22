-- ============================================================
-- 019_views.sql — reporting / listing views
-- All references match the live schema (ORM-aligned).
-- ============================================================

-- ── Product listing (storefront grids) ───────────────────────────────────────
CREATE OR REPLACE VIEW product_listing_view AS
SELECT
    p.id,
    p.slug,
    p.sku,
    p.name,
    p.base_price,
    p.compare_at_price,
    p.tax_rate,
    p.status,
    p.is_featured,
    p.is_new_arrival,
    p.is_best_seller,
    p.metal_type,
    p.gender,
    p.meta_title,
    p.meta_description,
    p.stock_quantity,
    c.id   AS category_id,
    c.name AS category_name,
    c.slug AS category_slug,
    COALESCE(rs.average_rating, 0) AS average_rating,
    COALESCE(rs.review_count, 0)   AS review_count,
    p.created_at,
    p.updated_at
FROM products p
LEFT JOIN categories c               ON c.id = p.category_id
LEFT JOIN product_rating_summary rs  ON rs.product_id = p.id
WHERE p.deleted_at IS NULL;

-- ── Order detail (admin dashboard) ───────────────────────────────────────────
CREATE OR REPLACE VIEW order_detail_view AS
SELECT
    o.id,
    o.order_number,
    o.status,
    o.payment_status,
    o.subtotal,
    o.discount,
    o.shipping_charge,
    o.tax_amount,
    o.total,
    o.payment_method,
    o.coupon_code,
    o.tracking_number,
    o.notes,
    o.created_at,
    o.updated_at,
    pr.id        AS customer_id,
    pr.full_name AS customer_name,
    pr.email     AS customer_email,
    pr.phone     AS customer_phone,
    o.shipping_full_name,
    o.shipping_line1,
    o.shipping_line2,
    o.shipping_city,
    o.shipping_state,
    o.shipping_postal,
    o.shipping_country
FROM orders o
JOIN profiles pr ON pr.id = o.user_id;

-- ── Revenue by day (paid orders only) ────────────────────────────────────────
CREATE OR REPLACE VIEW revenue_by_day AS
SELECT
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*)                      AS order_count,
    SUM(total)                    AS revenue
FROM orders
WHERE status NOT IN ('cancelled','refunded')
  AND payment_status = 'paid'
GROUP BY 1
ORDER BY 1 DESC;

-- ── Top products, trailing 30 days ───────────────────────────────────────────
CREATE OR REPLACE VIEW top_products_30d AS
SELECT
    p.id,
    p.name,
    p.slug,
    SUM(oi.quantity)                  AS units_sold,
    SUM(oi.quantity * oi.unit_price)  AS revenue
FROM order_items oi
JOIN orders   o ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
WHERE o.created_at >= NOW() - INTERVAL '30 days'
  AND o.status NOT IN ('cancelled','refunded')
GROUP BY p.id, p.name, p.slug
ORDER BY revenue DESC
LIMIT 20;

-- ── Inventory summary (admin) ────────────────────────────────────────────────
CREATE OR REPLACE VIEW inventory_summary_view AS
SELECT
    p.id            AS product_id,
    p.sku,
    p.name,
    p.stock_quantity,
    p.low_stock_threshold,
    p.track_inventory,
    p.allow_backorder,
    p.status,
    (p.stock_quantity <= p.low_stock_threshold) AS is_low_stock,
    c.name AS category_name
FROM products p
LEFT JOIN categories c ON c.id = p.category_id
WHERE p.deleted_at IS NULL;
