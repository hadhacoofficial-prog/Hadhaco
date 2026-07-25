-- ============================================================
-- collections_seed.sql
--
-- NOT a Redis-recovery script. Phase 3 of the CMS recovery effort
-- (Backend/supabase/recovery_reports/02_categories_and_config_recovery.md,
-- Section 4) confirmed the `collections:list:v1` Redis cache was empty at
-- capture time - there was no recovered collection data to restore. The 12
-- rows below are new seed content (names/descriptions/SEO copy), not
-- something recovered from cache, and are kept out of
-- Backend/supabase/recovery_sql/ so they aren't mistaken for recovered data.
--
-- Schema fix applied: `collections` has no `image_url` column (see
-- app/modules/collections/models.py:11-47). Like `categories`, a
-- collection's image is resolved at read time via a polymorphic join to
-- `images`/`image_variants` (owner_type='collection', owner_id=collection.id),
-- keyed off `primary_image_id` (an FK to images.id) - not a plain URL string
-- column. The original INSERT's `image_url` values have been dropped rather
-- than fabricating `images`/`image_variants` rows for them (those tables
-- have several NOT NULL fields - original_width/height/size_bytes, mime_type,
-- variant url/width/height/size_bytes per breakpoint - that cannot be
-- invented from a bare URL string).
--
-- ACTION NEEDED: upload each collection's image through the admin Media
-- Library (which populates images/image_variants correctly and sets
-- primary_image_id) rather than trying to seed it via SQL. The URLs from the
-- original INSERT are preserved in the comments below in case they point to
-- real, already-uploaded assets you want to attach that way.
--
-- Idempotent: INSERT ... ON CONFLICT (slug) DO UPDATE (upgraded from the
-- original's DO NOTHING so re-running this after an edit actually syncs the
-- new values, consistent with every other script in this recovery effort).
-- ============================================================

BEGIN;

INSERT INTO public.collections
    (name, slug, description, is_active, is_featured, sort_order, seo_title, seo_description)
VALUES
    -- image (not restorable via SQL, see header): https://cdn.hadha.co/collections/new-arrivals.jpg
    ('New Arrivals',           'new-arrivals',           'The latest additions to our 925 silver jewellery collection — fresh designs updated every week.',          TRUE, TRUE,   1, 'New Silver Jewellery Arrivals | Hadha.co',           'Discover the latest 925 silver jewellery at Hadha.co. New designs added weekly.'),
    -- image: https://cdn.hadha.co/collections/best-sellers.jpg
    ('Best Sellers',           'best-sellers',           'Our most loved silver jewellery — customer favourites trusted by thousands of shoppers.',                  TRUE, TRUE,   2, 'Best Selling Silver Jewellery | Hadha.co',           'Shop best selling 925 silver jewellery. Customer favourites in earrings, rings and more.'),
    -- image: https://cdn.hadha.co/collections/wedding-collection.jpg
    ('Wedding Collection',     'wedding-collection',     'Exquisite silver bridal jewellery — nakshi sets, temple pieces and statement designs for the big day.',    TRUE, TRUE,   3, 'Silver Bridal Jewellery Collection | Hadha.co',      'Explore our silver bridal jewellery. Nakshi sets, temple pieces and statement bridal designs.'),
    -- image: https://cdn.hadha.co/collections/temple-jewellery.jpg
    ('Temple Jewellery',       'temple-jewellery',       'Sacred temple-inspired silver jewellery — traditional motifs, deity designs and handcrafted masterpieces.', TRUE, FALSE,  4, 'Temple Silver Jewellery | Hadha.co',                 'Shop traditional temple silver jewellery. Sacred motifs and handcrafted temple designs.'),
    -- image: https://cdn.hadha.co/collections/office-wear.jpg
    ('Office Wear',            'office-wear',            'Subtle and sophisticated silver jewellery for the workplace — minimal, elegant and professional.',         TRUE, FALSE,  5, 'Silver Office Wear Jewellery | Hadha.co',            'Buy elegant silver jewellery for office wear. Minimal, sophisticated and professional.'),
    -- image: https://cdn.hadha.co/collections/daily-wear.jpg
    ('Daily Wear',             'daily-wear',             'Lightweight and comfortable silver jewellery for everyday use — durable, skin-friendly and versatile.',    TRUE, FALSE,  6, 'Daily Wear Silver Jewellery | Hadha.co',             'Shop daily wear 925 silver jewellery. Lightweight, comfortable and perfect for everyday use.'),
    -- image: https://cdn.hadha.co/collections/minimal-collection.jpg
    ('Minimal Collection',     'minimal-collection',     'Clean lines and understated elegance — minimalist silver jewellery for the modern aesthetic.',             TRUE, FALSE,  7, 'Minimal Silver Jewellery Collection | Hadha.co',     'Explore our minimal silver jewellery. Clean lines and understated elegance.'),
    -- image: https://cdn.hadha.co/collections/traditional-collection.jpg
    ('Traditional Collection', 'traditional-collection', 'Rich heritage and timeless craftsmanship — traditional Indian silver jewellery rooted in culture.',        TRUE, FALSE,  8, 'Traditional Silver Jewellery | Hadha.co',            'Shop traditional Indian silver jewellery. Rich heritage and timeless craftsmanship.'),
    -- image: https://cdn.hadha.co/collections/festive-collection.jpg
    ('Festive Collection',     'festive-collection',     'Vibrant and celebratory silver jewellery — perfect for Diwali, Navratri, Eid and every festival.',        TRUE, TRUE,   9, 'Festive Silver Jewellery Collection | Hadha.co',     'Buy festive silver jewellery for Diwali, Navratri and every celebration.'),
    -- image: https://cdn.hadha.co/collections/premium-collection.jpg
    ('Premium Collection',     'premium-collection',     'Our finest handcrafted pieces — premium silver jewellery with exceptional detail and superior finish.',    TRUE, FALSE, 10, 'Premium Silver Jewellery Collection | Hadha.co',     'Explore premium 925 silver jewellery. Finest handcrafted pieces with exceptional detail.'),
    -- image: https://cdn.hadha.co/collections/kids-collection.jpg
    ('Kids Collection',        'kids-collection',        'Safe, certified and adorable silver jewellery for children — skin-friendly, lightweight and fun.',         TRUE, FALSE, 11, 'Kids Silver Jewellery Collection | Hadha.co',        'Shop kids silver jewellery at Hadha.co. Safe, certified and adorable designs.'),
    -- image: https://cdn.hadha.co/collections/men-collection.jpg
    ('Men Collection',         'men-collection',         'Bold, rugged and refined silver jewellery for men — chains, rings, kadas and contemporary accessories.',   TRUE, FALSE, 12, 'Men''s Silver Jewellery Collection | Hadha.co',      'Explore men''s silver jewellery. Bold chains, rings, kadas and accessories.')
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    is_featured = EXCLUDED.is_featured,
    sort_order = EXCLUDED.sort_order,
    seo_title = EXCLUDED.seo_title,
    seo_description = EXCLUDED.seo_description,
    updated_at = NOW();

COMMIT;
