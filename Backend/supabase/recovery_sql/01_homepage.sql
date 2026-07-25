-- ============================================================
-- 01_homepage.sql
-- Homepage CMS restoration, recovered from the Redis cache key
-- `cms:homepage` (decoded payload: recovery-backup/Json data/cms_homepage.json).
-- Cache write timestamp (epoch, from the cache_swr wrapper's "t" field): 1784983802.1023817
--
-- SCOPE: Homepage CMS only -> landing_sections + cms_section_items.
-- Categories, Products, Collections, Navigation and Company Config are
-- OUT OF SCOPE for this script and are not touched.
--
-- Idempotent: every statement is INSERT ... ON CONFLICT DO UPDATE.
-- No DELETE, no TRUNCATE. Safe to run multiple times.
-- See Backend/supabase/recovery_reports/01_homepage_recovery.md for the
-- full schema mapping, per-section confidence levels and unresolved fields.
-- ============================================================

BEGIN;

-- ── 1. landing_sections (16 rows = full homepage layout) ──────────────────

-- section_key = announcement_bar  (section_type = announcement_bar)
-- id recovered from cms_section_items.section_id (3 item(s) below reference it)
INSERT INTO landing_sections
    (id, section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('bc6c2286-9194-416f-9a35-5e9a98b1482d', 'announcement_bar', 'announcement_bar', 'Announcement Bar',
     $hpj${"show_close": true, "rotation_speed": 4}$hpj$::jsonb,
     $hpj${"show_close": true, "rotation_speed": 4}$hpj$::jsonb,
     TRUE, 0, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    id = EXCLUDED.id,
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = navbar  (section_type = navbar)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('navbar', 'navbar', 'Navbar',
     $hpj${}$hpj$::jsonb,
     $hpj${}$hpj$::jsonb,
     TRUE, 10, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = hero_carousel  (section_type = hero_carousel)
-- id recovered from cms_section_items.section_id (1 item(s) below reference it)
INSERT INTO landing_sections
    (id, section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('294bf305-3b09-48ca-b979-ded8449712b8', 'hero_carousel', 'hero_carousel', 'Hero Carousel',
     $hpj${"height": "large", "transition": "slide", "auto_rotate": false, "pause_on_hover": true, "rotation_speed": 30, "schema_version": 2, "transition_duration": "normal"}$hpj$::jsonb,
     $hpj${"height": "large", "transition": "slide", "auto_rotate": false, "pause_on_hover": true, "rotation_speed": 30, "schema_version": 2, "transition_duration": "normal"}$hpj$::jsonb,
     TRUE, 10, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    id = EXCLUDED.id,
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = featured_collection  (section_type = collection_showcase)
-- id recovered from cms_section_items.section_id (2 item(s) below reference it)
INSERT INTO landing_sections
    (id, section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('5f104219-6fdd-44fb-b379-4545021e3a80', 'featured_collection', 'collection_showcase', 'Featured Collection',
     $hpj${"title": "Featured Collection", "grid_size": "3", "card_style": "overlay"}$hpj$::jsonb,
     $hpj${"title": "Featured Collection", "grid_size": "3", "card_style": "overlay"}$hpj$::jsonb,
     TRUE, 20, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    id = EXCLUDED.id,
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = featured_products  (section_type = product_grid)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('featured_products', 'product_grid', 'Featured Products',
     $hpj${"title": "Handpicked for You", "source": "featured", "eyebrow": "Featured Products", "max_products": 8, "view_all_url": "/products"}$hpj$::jsonb,
     $hpj${"title": "Handpicked for You", "source": "featured", "eyebrow": "Featured Products", "max_products": 8, "view_all_url": "/products"}$hpj$::jsonb,
     TRUE, 30, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = shop_by_gender  (section_type = category_grid)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('shop_by_gender', 'category_grid', 'Shop by Gender',
     $hpj${"title": "Shop by Style", "columns": 4}$hpj$::jsonb,
     $hpj${"title": "Shop by Style", "columns": 4}$hpj$::jsonb,
     TRUE, 30, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = craftsmanship_video  (section_type = video_section)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('craftsmanship_video', 'video_section', 'Craftsmanship Video',
     $hpj${"loop": true, "muted": true, "title": "Cast by hand in our Visakhapatnam atelier.", "eyebrow": "Our Craftsmanship", "mp4_url": "https://cdn.hadha.co/cms/video/dc1573e3-3526-46d8-9a2f-bde26b89b90f.mp4", "autoplay": true, "controls": false, "subtitle": "Every Hadha piece is shaped, polished and quality-checked by our master silversmiths — keeping South Indian artisanship alive, one creation at a time.", "poster_url": "https://cdn.hadha.co/cms/video/79fd276e-1f06-41fc-8afd-2e35409cbd7d.jpg"}$hpj$::jsonb,
     $hpj${"loop": true, "muted": true, "title": "Cast by hand in our Visakhapatnam atelier.", "eyebrow": "Our Craftsmanship", "mp4_url": "https://cdn.hadha.co/cms/video/dc1573e3-3526-46d8-9a2f-bde26b89b90f.mp4", "autoplay": true, "controls": false, "subtitle": "Every Hadha piece is shaped, polished and quality-checked by our master silversmiths — keeping South Indian artisanship alive, one creation at a time.", "poster_url": "https://cdn.hadha.co/cms/video/79fd276e-1f06-41fc-8afd-2e35409cbd7d.jpg"}$hpj$::jsonb,
     TRUE, 40, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = new_arrivals  (section_type = product_grid)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('new_arrivals', 'product_grid', 'New Arrivals',
     $hpj${"title": "New Arrivals", "source": "newest", "eyebrow": "Just In", "max_products": 8, "view_all_url": "/products?sort=newest"}$hpj$::jsonb,
     $hpj${"title": "New Arrivals", "source": "newest", "eyebrow": "Just In", "max_products": 8, "view_all_url": "/products?sort=newest"}$hpj$::jsonb,
     TRUE, 50, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = promo_banner  (section_type = image_banner)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('promo_banner', 'image_banner', 'Promo Banner',
     $hpj${"title": "STUDS", "cta_url": "https://hadha.co/products?gender=women&category=women-stud-earrings", "cta_text": "Shop the STUDS", "subtitle": "Press-on temple silhouettes in solid 92.5 silver.", "overlay_opacity": 0.25, "mobile_image_url": "https://cdn.hadha.co/cms/banners/dd49cc98-ca78-41c1-a43e-d98a580a76bc.jpg", "desktop_image_url": "https://cdn.hadha.co/cms/banners/c6f72380-25b1-4100-b400-00f9b7ca8a6a.jpg"}$hpj$::jsonb,
     $hpj${"title": "STUDS", "cta_url": "https://hadha.co/products?gender=women&category=women-stud-earrings", "cta_text": "Shop the STUDS", "subtitle": "Press-on temple silhouettes in solid 92.5 silver.", "overlay_opacity": 0.25, "mobile_image_url": "https://cdn.hadha.co/cms/banners/dd49cc98-ca78-41c1-a43e-d98a580a76bc.jpg", "desktop_image_url": "https://cdn.hadha.co/cms/banners/c6f72380-25b1-4100-b400-00f9b7ca8a6a.jpg"}$hpj$::jsonb,
     TRUE, 60, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = trending  (section_type = product_grid)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('trending', 'product_grid', 'Trending',
     $hpj${"title": "Trending Now", "source": "best_seller", "eyebrow": "Most loved", "max_products": 8, "view_all_url": "/products?sort=trending"}$hpj$::jsonb,
     $hpj${"title": "Trending Now", "source": "best_seller", "eyebrow": "Most loved", "max_products": 8, "view_all_url": "/products?sort=trending"}$hpj$::jsonb,
     TRUE, 70, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = shop_by_category  (section_type = category_grid)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('shop_by_category', 'category_grid', 'Shop by Category',
     $hpj${"title": "Shop by Category", "columns": 3}$hpj$::jsonb,
     $hpj${"title": "Shop by Category", "columns": 3}$hpj$::jsonb,
     TRUE, 80, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = why_choose_us  (section_type = content_block)
-- id recovered from cms_section_items.section_id (8 item(s) below reference it)
INSERT INTO landing_sections
    (id, section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 'why_choose_us', 'content_block', 'Why Choose Us',
     $hpj${"title": "Why Hadha"}$hpj$::jsonb,
     $hpj${"title": "Why Hadha"}$hpj$::jsonb,
     TRUE, 80, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    id = EXCLUDED.id,
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = reviews  (section_type = testimonials)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('reviews', 'testimonials', 'Customer Reviews',
     $hpj${"sort": "recent", "title": "What Our Customers Say"}$hpj$::jsonb,
     $hpj${"sort": "recent", "title": "What Our Customers Say"}$hpj$::jsonb,
     TRUE, 90, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = instagram_gallery  (section_type = instagram_gallery)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('instagram_gallery', 'instagram_gallery', 'Instagram Gallery',
     $hpj${"title": "Worn by our community.", "handle": "https://www.instagram.com/hadha92.5silver", "source": "collections", "max_items": 6}$hpj$::jsonb,
     $hpj${"title": "Worn by our community.", "handle": "https://www.instagram.com/hadha92.5silver", "source": "collections", "max_items": 6}$hpj$::jsonb,
     TRUE, 100, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = newsletter  (section_type = newsletter)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('newsletter', 'newsletter', 'Newsletter',
     $hpj${"heading": "Be first to know.", "btn_text": "Subscribe", "description": "Join the Hadha circle for early access to drops, members-only edits, and quiet little gifts.", "placeholder": "Your email address", "success_message": "Welcome to the Hadha Circle!"}$hpj$::jsonb,
     $hpj${"heading": "Be first to know.", "btn_text": "Subscribe", "description": "Join the Hadha circle for early access to drops, members-only edits, and quiet little gifts.", "placeholder": "Your email address", "success_message": "Welcome to the Hadha Circle!"}$hpj$::jsonb,
     TRUE, 110, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- section_key = footer  (section_type = footer)
-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict
INSERT INTO landing_sections
    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)
VALUES
    ('footer', 'footer', 'Footer',
     $hpj${"email": "hello@hadha.co", "phone": "+91 9160941585", "youtube": "", "facebook": "", "whatsapp": "+919160941585", "instagram": "", "description": "Popula Dabba's Hadha — premium 92.5 silver jewellery rooted in South Indian heritage, made for everyday and treasured for a lifetime.", "copyright_name": "Hadha Silver Jewellery", "company_address": "Hyderabad,500018"}$hpj$::jsonb,
     $hpj${"email": "hello@hadha.co", "phone": "+91 9160941585", "youtube": "", "facebook": "", "whatsapp": "+919160941585", "instagram": "", "description": "Popula Dabba's Hadha — premium 92.5 silver jewellery rooted in South Indian heritage, made for everyday and treasured for a lifetime.", "copyright_name": "Hadha Silver Jewellery", "company_address": "Hyderabad,500018"}$hpj$::jsonb,
     TRUE, 120, 'published', 1, NOW(), NOW())
ON CONFLICT (section_key) DO UPDATE SET
    section_type = EXCLUDED.section_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    status = EXCLUDED.status,
    updated_at = NOW();

-- ── 2. cms_section_items (recovered items for the 4 sections that had any) ─
--
-- NOTE (why_choose_us anomaly, preserved verbatim, not deduplicated):
-- the cache contains 8 items for 4 distinct cards - each card appears twice
-- under two different UUIDs with two different created_at/updated_at pairs
-- but otherwise byte-identical config. This looks like a duplicate-publish
-- artifact in the source system, not a decoding error. Per the 'never invent,
-- never silently alter recovered data' rule, all 8 rows are restored exactly
-- as cached. See the recovery report for the flagged anomaly.

-- items for section_key = announcement_bar  (section_id = bc6c2286-9194-416f-9a35-5e9a98b1482d)
INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('7c003889-1103-45a0-b32a-32e2a8d9d50a', 'bc6c2286-9194-416f-9a35-5e9a98b1482d', 0, TRUE,
     $hpj${"text": "FREE SHIPPING ABOVE ₹999", "bg_color": "#0F2340", "text_color": "#FFFFFF"}$hpj$::jsonb,
     '2026-07-24T07:09:25.436714Z'::timestamptz, '2026-07-24T07:09:25.436720Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('f5d4b31c-54a0-41fc-a965-8aff20e25dc8', 'bc6c2286-9194-416f-9a35-5e9a98b1482d', 10, TRUE,
     $hpj${"text": "Certified 92.5 Sterling Silver", "bg_color": "#0F2340", "text_color": "#FFFFFF"}$hpj$::jsonb,
     '2026-07-24T07:09:25.464791Z'::timestamptz, '2026-07-24T07:09:25.464796Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('79421254-bcd8-4f11-a998-f522d543c8c3', 'bc6c2286-9194-416f-9a35-5e9a98b1482d', 20, TRUE,
     $hpj${"text": "premium 92.5 silver jewellery", "bg_color": "#0F2340", "text_color": "#FFFFFF"}$hpj$::jsonb,
     '2026-07-24T07:09:25.635530Z'::timestamptz, '2026-07-24T07:09:25.635535Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

-- items for section_key = hero_carousel  (section_id = 294bf305-3b09-48ca-b979-ded8449712b8)
INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('34d987b0-9e13-4013-94b2-9c52da20ef81', '294bf305-3b09-48ca-b979-ded8449712b8', 20, TRUE,
     $hpj${"media": {"mobile_image_url": "https://cdn.hadha.co/images/hero_mobile/cms_section_item/34d987b0-9e13-4013-94b2-9c52da20ef81/9b779d5d-1fea-4ffe-a01c-456faed32ad1/mobile/hero-mobile@1x.webp?v=2", "desktop_image_url": "https://cdn.hadha.co/images/hero_desktop/cms_section_item/34d987b0-9e13-4013-94b2-9c52da20ef81/48d9ddbb-54ed-4f73-a5ac-a6471c062861/desktop/hero-desktop@1x.webp?v=2"}, "colors": {"text": "white", "eyebrow": "white", "gradient": false, "overlay_color": "dark", "overlay_opacity": 0}, "layout": {"preset": "editorial"}, "buttons": {"primary_color": "navy", "primary_style": "filled", "secondary_color": "white", "secondary_style": "outline"}, "content": {"eyebrow": "HELLO", "seo_alt": "HADHA 92.5 SILVER ", "headline": "WELCOME ", "subheading": "", "primary_btn_url": "https://hadha.co/", "primary_btn_text": "Shop Now"}, "typography": {"headline_font": "display", "headline_weight": "bold", "description_size": "large"}}$hpj$::jsonb,
     '2026-07-24T10:46:18.707298Z'::timestamptz, '2026-07-25T11:04:36.594358Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

-- items for section_key = featured_collection  (section_id = 5f104219-6fdd-44fb-b379-4545021e3a80)
INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('83734da5-17ba-4d7e-9792-e8acfb5c3a14', '5f104219-6fdd-44fb-b379-4545021e3a80', 0, TRUE,
     $hpj${"title": "Stylish Chains redefined.", "eyebrow": "Featured edit", "subtitle": "Stylish Chains crafted to bring subtle elegance to every look — from stackable everyday bands to statement temple stones.", "image_url": "https://cdn.hadha.co/cms/collections/72ed8200-9516-4d35-8032-bf73d59427d7.jpg", "button_url": "/collections", "button_text": "Shop bangles", "hover_image_url": "https://cdn.hadha.co/cms/collections/72270b32-da4e-4782-9e55-73bf0734d840.jpg"}$hpj$::jsonb,
     '2026-07-02T18:22:08.810598Z'::timestamptz, '2026-07-05T02:10:41.300144Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('8b6a29b0-936c-40ac-a67d-c87fd61d7490', '5f104219-6fdd-44fb-b379-4545021e3a80', 10, TRUE,
     $hpj${"title": "The studes", "eyebrow": "Bestseller", "subtitle": "Heritage temple ear cuffs reimagined — non-piercing, press-on, and poised to become your new favourite.", "image_url": "https://cdn.hadha.co/cms/collections/cf7257b7-02a8-47aa-a1e9-6588ee1e9d4b.jpg", "button_url": "/collections", "button_text": "Discover studs", "hover_image_url": "https://cdn.hadha.co/cms/collections/e22736dd-f878-4b84-ac86-88b5bfdda709.jpg"}$hpj$::jsonb,
     '2026-07-02T18:22:09.064800Z'::timestamptz, '2026-07-05T02:10:41.196928Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

-- items for section_key = why_choose_us  (section_id = f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88)
INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('011373b9-0c9a-4ce0-8125-6ae7ffe3e34c', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 0, TRUE,
     $hpj${"icon": "shield", "text": "BIS-hallmarked. Guaranteed purity in every piece we craft.", "title": "92.5 Sterling Silver"}$hpj$::jsonb,
     '2026-07-25T11:15:02.869396Z'::timestamptz, '2026-07-25T11:15:02.869404Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('7a92f13a-ff1a-4720-9256-c228f53364ea', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 0, TRUE,
     $hpj${"icon": "shield", "text": "BIS-hallmarked. Guaranteed purity in every piece we craft.", "title": "92.5 Sterling Silver"}$hpj$::jsonb,
     '2026-07-25T11:15:00.285699Z'::timestamptz, '2026-07-25T11:15:00.285705Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('65e102ac-1943-4e15-b6c1-3a00d5c86f2a', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 10, TRUE,
     $hpj${"icon": "gem", "text": "EXPERIENCE THE AUTHENTIC AND PREMIUM QUALITY MOST STYLISH SILVER JEWELLERY", "title": "Authentic Craftsmanship"}$hpj$::jsonb,
     '2026-07-25T11:15:02.636017Z'::timestamptz, '2026-07-25T11:15:02.636021Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('f391a826-168a-4c9e-8cde-cffb94650805', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 10, TRUE,
     $hpj${"icon": "gem", "text": "EXPERIENCE THE AUTHENTIC AND PREMIUM QUALITY MOST STYLISH SILVER JEWELLERY", "title": "Authentic Craftsmanship"}$hpj$::jsonb,
     '2026-07-25T11:15:00.235513Z'::timestamptz, '2026-07-25T11:15:00.235518Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('7a5a13dd-b281-4bc4-9a7d-2de570f674ab', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 20, TRUE,
     $hpj${"icon": "sparkles", "text": "Anti-tarnish coating and lifetime polish on every Hadha creation.", "title": "Trusted Quality"}$hpj$::jsonb,
     '2026-07-25T11:15:00.237333Z'::timestamptz, '2026-07-25T11:15:00.237339Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('63f45064-af1b-42dd-8a40-9a04660c990c', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 20, TRUE,
     $hpj${"icon": "sparkles", "text": "Anti-tarnish coating and lifetime polish on every Hadha creation.", "title": "Trusted Quality"}$hpj$::jsonb,
     '2026-07-25T11:15:02.723650Z'::timestamptz, '2026-07-25T11:15:02.723655Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('23d6bfa2-16c7-48e2-9f69-26dd713dea20', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 30, TRUE,
     $hpj${"icon": "heart", "text": "A family heirloom in the making — gift-wrapped and delivered with care.", "title": "Made With Love"}$hpj$::jsonb,
     '2026-07-25T11:15:00.318087Z'::timestamptz, '2026-07-25T11:15:00.318093Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

INSERT INTO cms_section_items
    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)
VALUES
    ('7b20f97f-ffbc-4d3b-b0ca-cbcf9968bc2c', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88', 30, TRUE,
     $hpj${"icon": "heart", "text": "A family heirloom in the making — gift-wrapped and delivered with care.", "title": "Made With Love"}$hpj$::jsonb,
     '2026-07-25T11:15:02.902467Z'::timestamptz, '2026-07-25T11:15:02.902473Z'::timestamptz)
ON CONFLICT (id) DO UPDATE SET
    section_id = EXCLUDED.section_id,
    sort_order = EXCLUDED.sort_order,
    is_enabled = EXCLUDED.is_enabled,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at;

-- ── 3. In-transaction validation ─────────────────────────────────────────
-- Aborts the whole restore (ROLLBACK) if the row counts don't match what was
-- recovered from the cache, instead of committing a partial/mismatched state.
DO $$
DECLARE
    section_count INTEGER;
    item_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO section_count FROM landing_sections WHERE section_key IN (
        'announcement_bar', 'navbar', 'hero_carousel', 'featured_collection', 'featured_products', 'shop_by_gender', 'craftsmanship_video', 'new_arrivals', 'promo_banner', 'trending', 'shop_by_category', 'why_choose_us', 'reviews', 'instagram_gallery', 'newsletter', 'footer');
    IF section_count <> 16 THEN
        RAISE EXCEPTION 'homepage restore validation failed: expected 16 landing_sections rows, found %', section_count;
    END IF;

    SELECT COUNT(*) INTO item_count FROM cms_section_items WHERE section_id IN (
        'bc6c2286-9194-416f-9a35-5e9a98b1482d', '294bf305-3b09-48ca-b979-ded8449712b8', '5f104219-6fdd-44fb-b379-4545021e3a80', 'f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88');
    IF item_count < 14 THEN
        RAISE EXCEPTION 'homepage restore validation failed: expected at least 14 cms_section_items rows across recovered sections, found %', item_count;
    END IF;
    -- Uses >= rather than = : admins may legitimately add more items to
    -- these sections after this restore runs once; re-running the script
    -- later must not fail just because the count grew past the recovered
    -- baseline.

    RAISE NOTICE 'Homepage CMS restore validated: % landing_sections, % cms_section_items', section_count, item_count;
END $$;

COMMIT;
