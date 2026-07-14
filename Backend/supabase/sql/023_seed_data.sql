-- ============================================================
-- 023_seed_data.sql — initial reference/config data
-- Idempotent: all inserts use ON CONFLICT DO NOTHING.
-- ============================================================

-- ── Feature flags ─────────────────────────────────────────────────────────────
-- complimentary_gift_enabled is seeded by Alembic migration 0036.
-- No other feature flags are wired up; add new flags here only when the
-- corresponding backend + frontend enforcement code exists.

-- ── App settings ──────────────────────────────────────────────────────────────
INSERT INTO app_settings (key, value, description) VALUES
    ('currency_code',       '"INR"',  'ISO 4217 currency code'),
    ('currency_symbol',     '"₹"',    'Currency display symbol'),
    ('free_shipping_above', '999',    'Cart total for free shipping eligibility (INR)'),
    ('return_window_days',  '7',      'Days after delivery to allow returns'),
    ('min_order_amount',    '299',    'Minimum cart total to place order (INR)'),
    ('gst_rate_percent',    '3',      'GST rate for hallmarked silver jewellery'),
    ('store_state_code',    '"MH"',   'Seller state code for CGST/SGST vs IGST split')
ON CONFLICT (key) DO NOTHING;

-- ── Categories (silver jewellery storefront) ──────────────────────────────────
INSERT INTO categories (name, slug, description, sort_order, is_active) VALUES
    ('Rings',           'rings',            '925 silver rings for every occasion',          1,  TRUE),
    ('Anklets',         'anklets',          'Traditional and contemporary silver anklets',  2,  TRUE),
    ('Bracelets',       'bracelets',        'Silver bracelets and kadas',                   3,  TRUE),
    ('Chains',          'chains',           'Sterling silver chains',                       4,  TRUE),
    ('Necklaces',       'necklaces',        'Silver necklaces and sets',                    5,  TRUE),
    ('Pendants',        'pendants',         'Silver pendants and lockets',                  6,  TRUE),
    ('Bangles',         'bangles',          'Silver bangles',                               7,  TRUE),
    ('Earrings',        'earrings',         'Studs, jhumkas, hoops and drops',              8,  TRUE),
    ('Toe Rings',       'toe-rings',        'Traditional silver toe rings',                 9,  TRUE),
    ('Kids Jewellery',  'kids-jewellery',   'Safe silver jewellery for kids',              10,  TRUE),
    ('Men Jewellery',   'men-jewellery',    'Silver jewellery for men',                    11,  TRUE),
    ('Black Bead Sets', 'black-bead-sets',  'Nazariya and black bead jewellery',           12,  TRUE),
    ('Nakshi',          'nakshi',           'Handcrafted Nakshi work jewellery',           13,  TRUE),
    ('Bugadi',          'bugadi',           'Traditional Maharashtrian nose rings',        14,  TRUE)
ON CONFLICT (slug) DO NOTHING;

-- ── Notification templates ────────────────────────────────────────────────────
-- Columns match 012_notifications.sql / app/modules/notifications/models.py:
--   (name, channel, event_type, subject, template_body, is_active)
-- event_type values match app/modules/notifications/service.py listeners.
INSERT INTO notification_templates (name, channel, event_type, subject, template_body, is_active) VALUES
(
    'welcome_email', 'email', 'user_registered',
    'Welcome to Hadha.co ✨',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Welcome, {{full_name}}!</h2><p style="color:#555;line-height:1.6;">Thank you for joining Hadha.co — your home for handcrafted 925 silver jewellery. Explore our collections of rings, anklets, necklaces and more.</p><p style="text-align:center;margin:28px 0;"><a href="https://hadha.co/collections" style="background:#1c1b1a;color:#fff;text-decoration:none;padding:12px 28px;border-radius:4px;display:inline-block;">Start Shopping</a></p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver · <a href="https://hadha.co/contact" style="color:#999;">Contact us</a></td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'order_confirmation_email', 'email', 'order_created',
    'Your Hadha order {{order_number}} is confirmed',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Thank you for your order!</h2><p style="color:#555;line-height:1.6;">Order <strong>{{order_number}}</strong> has been received. Total: <strong>₹{{total}}</strong>. We will email you again as soon as it ships.</p><p style="text-align:center;margin:28px 0;"><a href="https://hadha.co/orders/{{order_number}}" style="background:#1c1b1a;color:#fff;text-decoration:none;padding:12px 28px;border-radius:4px;display:inline-block;">View Order</a></p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver</td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'payment_receipt_email', 'email', 'payment_captured',
    'Payment received for order {{order_number}}',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Payment received ✓</h2><p style="color:#555;line-height:1.6;">We received your payment of <strong>₹{{amount}}</strong> for order <strong>{{order_number}}</strong>. Your jewellery is now being prepared with care.</p><p style="text-align:center;margin:28px 0;"><a href="https://hadha.co/orders/{{order_number}}" style="background:#1c1b1a;color:#fff;text-decoration:none;padding:12px 28px;border-radius:4px;display:inline-block;">Track Order</a></p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver</td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'order_shipped_email', 'email', 'order_shipped',
    'Your order {{order_number}} has shipped 🚚',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Your order is on its way!</h2><p style="color:#555;line-height:1.6;">Order <strong>{{order_number}}</strong> has shipped. Tracking number (AWB): <strong>{{awb}}</strong>.</p><p style="text-align:center;margin:28px 0;"><a href="{{tracking_url}}" style="background:#1c1b1a;color:#fff;text-decoration:none;padding:12px 28px;border-radius:4px;display:inline-block;">Track Shipment</a></p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver</td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'order_delivered_email', 'email', 'order_delivered',
    'Your order {{order_number}} has been delivered',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Delivered! 🎉</h2><p style="color:#555;line-height:1.6;">Order <strong>{{order_number}}</strong> has been delivered. We hope you love your Hadha jewellery. Care tip: store silver in a dry pouch and keep away from perfume.</p><p style="text-align:center;margin:28px 0;"><a href="https://hadha.co/orders/{{order_number}}" style="background:#1c1b1a;color:#fff;text-decoration:none;padding:12px 28px;border-radius:4px;display:inline-block;">View Order</a></p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver</td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'refund_created_email', 'email', 'refund_created',
    'Refund initiated for order {{order_number}}',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Refund initiated</h2><p style="color:#555;line-height:1.6;">A refund of <strong>₹{{amount}}</strong> for order <strong>{{order_number}}</strong> has been initiated. You will receive a confirmation once it is processed by your bank.</p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver</td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'refund_processed_email', 'email', 'refund_processed',
    'Refund of ₹{{amount}} processed for order {{order_number}}',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Refund processed ✓</h2><p style="color:#555;line-height:1.6;">Your refund of <strong>₹{{amount}}</strong> for order <strong>{{order_number}}</strong> has been processed. It should reach your account within 5–7 business days.</p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver</td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'review_request_email', 'email', 'review_request',
    'How was your Hadha order {{order_number}}?',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Share your experience</h2><p style="color:#555;line-height:1.6;">We hope you are loving your jewellery from order <strong>{{order_number}}</strong>. Your review helps other shoppers and takes less than a minute.</p><p style="text-align:center;margin:28px 0;"><a href="https://hadha.co/orders/{{order_number}}/review" style="background:#1c1b1a;color:#fff;text-decoration:none;padding:12px 28px;border-radius:4px;display:inline-block;">Write a Review</a></p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver</td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'low_stock_alert_email', 'email', 'low_inventory_alert',
    '[Hadha Admin] Low stock: {{product_name}} ({{sku}})',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#8a1c1c;padding:16px 32px;text-align:center;"><span style="color:#fff;font-size:18px;letter-spacing:2px;">HADHA ADMIN ALERT</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Low stock warning</h2><p style="color:#555;line-height:1.6;">Product <strong>{{product_name}}</strong> (SKU <strong>{{sku}}</strong>) is down to <strong>{{qty}}</strong> units. Restock soon to avoid losing sales.</p></td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'abandoned_cart_email', 'email', 'abandoned_cart',
    'You left something sparkly behind ✨',
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;"><tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;"><span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span></td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">Still thinking it over{% if full_name %}, {{full_name}}{% endif %}?</h2><p style="color:#555;line-height:1.6;">You have {{item_count}} item(s) waiting in your cart. Complete your order before they sell out.</p><p style="text-align:center;margin:28px 0;"><a href="https://hadha.co/cart" style="background:#1c1b1a;color:#fff;text-decoration:none;padding:12px 28px;border-radius:4px;display:inline-block;">Return to Cart</a></p></td></tr><tr><td style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver</td></tr></table></td></tr></table></body></html>',
    TRUE
),
(
    'order_confirmation_sms', 'sms', 'order_created',
    NULL,
    'Thank you for shopping with Hadha.co. Your order {{order_number}} has been confirmed. Track it at https://hadha.co/orders/{{order_number}}',
    TRUE
)
ON CONFLICT (name) DO NOTHING;

-- ── Admin bootstrap ───────────────────────────────────────────────────────────
-- The first super admin must sign up through Supabase Auth (so auth.users and
-- profiles rows exist), then run:
--   UPDATE profiles SET role = 'super_admin' WHERE email = 'admin@hadha.co';
