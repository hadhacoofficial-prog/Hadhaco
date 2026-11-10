-- ============================================================
-- 03_company_config.sql
-- Company config restoration, recovered from the Redis cache key
-- `company:config` (decoded payload:
-- recovery-backup/Json data/company_config.json).
-- Cache write timestamp (epoch): 1784983769.5432687
--
-- SCOPE: `company_config` table ONLY - a singleton row (id = 1,
-- seeded once by alembic/versions/0013_company_config.py).
--
-- All 38 fields the public GET /company/config endpoint returns are
-- present in the cache and restored verbatim. Model-only fields the public
-- API never serializes (e.g. logo_r2_key) are absent from the cache and are
-- NOT included in this statement's SET clause, so an existing value (if any)
-- is left untouched rather than being wiped to NULL.
--
-- Idempotent: INSERT ... ON CONFLICT (id) DO UPDATE. No DELETE/TRUNCATE.
-- ============================================================

BEGIN;

INSERT INTO company_config
    (id, name, legal_name, brand_name, tagline, description, website, domain, logo_url, favicon_url, packing_slip_logo_url, shipping_label_logo_url, phone, alternate_phone, whatsapp, support_email, sales_email, address_line_1, address_line_2, city, state, postal_code, country, google_maps_url, latitude, longitude, gstin, cin, business_hours, instagram_url, facebook_url, youtube_url, twitter_x_url, linkedin_url, pinterest_url, default_meta_title, default_meta_description, organization_description, theme_color)
VALUES
    (1,
     'Hadha Co',  -- name
     NULL,  -- legal_name
     NULL,  -- brand_name
     'The Strong Decision : The Choice is Yours. The Quality is Ours.',  -- tagline
     NULL,  -- description
     'www.hadha.co',  -- website
     NULL,  -- domain
     NULL,  -- logo_url
     NULL,  -- favicon_url
     NULL,  -- packing_slip_logo_url
     NULL,  -- shipping_label_logo_url
     '9160941585',  -- phone
     NULL,  -- alternate_phone
     '9160941585',  -- whatsapp
     'support@hadha.co',  -- support_email
     NULL,  -- sales_email
     NULL,  -- address_line_1
     NULL,  -- address_line_2
     'hyderbad',  -- city
     'telangana',  -- state
     '500081',  -- postal_code
     'IN',  -- country
     NULL,  -- google_maps_url
     NULL,  -- latitude
     NULL,  -- longitude
     '37BTBPP8717J1Z7',  -- gstin
     NULL,  -- cin
     NULL,  -- business_hours
     NULL,  -- instagram_url
     NULL,  -- facebook_url
     NULL,  -- youtube_url
     NULL,  -- twitter_x_url
     NULL,  -- linkedin_url
     NULL,  -- pinterest_url
     NULL,  -- default_meta_title
     NULL,  -- default_meta_description
     NULL,  -- organization_description
     NULL  -- theme_color
    )
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    legal_name = EXCLUDED.legal_name,
    brand_name = EXCLUDED.brand_name,
    tagline = EXCLUDED.tagline,
    description = EXCLUDED.description,
    website = EXCLUDED.website,
    domain = EXCLUDED.domain,
    logo_url = EXCLUDED.logo_url,
    favicon_url = EXCLUDED.favicon_url,
    packing_slip_logo_url = EXCLUDED.packing_slip_logo_url,
    shipping_label_logo_url = EXCLUDED.shipping_label_logo_url,
    phone = EXCLUDED.phone,
    alternate_phone = EXCLUDED.alternate_phone,
    whatsapp = EXCLUDED.whatsapp,
    support_email = EXCLUDED.support_email,
    sales_email = EXCLUDED.sales_email,
    address_line_1 = EXCLUDED.address_line_1,
    address_line_2 = EXCLUDED.address_line_2,
    city = EXCLUDED.city,
    state = EXCLUDED.state,
    postal_code = EXCLUDED.postal_code,
    country = EXCLUDED.country,
    google_maps_url = EXCLUDED.google_maps_url,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    gstin = EXCLUDED.gstin,
    cin = EXCLUDED.cin,
    business_hours = EXCLUDED.business_hours,
    instagram_url = EXCLUDED.instagram_url,
    facebook_url = EXCLUDED.facebook_url,
    youtube_url = EXCLUDED.youtube_url,
    twitter_x_url = EXCLUDED.twitter_x_url,
    linkedin_url = EXCLUDED.linkedin_url,
    pinterest_url = EXCLUDED.pinterest_url,
    default_meta_title = EXCLUDED.default_meta_title,
    default_meta_description = EXCLUDED.default_meta_description,
    organization_description = EXCLUDED.organization_description,
    theme_color = EXCLUDED.theme_color
;

-- ── Validation ───────────────────────────────────────────────────────────
DO $$
DECLARE
    cfg_name TEXT;
BEGIN
    SELECT name INTO cfg_name FROM company_config WHERE id = 1;
    IF cfg_name IS NULL THEN
        RAISE EXCEPTION 'company_config restore validation failed: no row with id=1 after restore';
    END IF;
    IF cfg_name <> 'Hadha Co' THEN
        RAISE EXCEPTION 'company_config restore validation failed: expected name %, found %', 'Hadha Co', cfg_name;
    END IF;
    RAISE NOTICE 'company_config restore validated: name = %', cfg_name;
END $$;

COMMIT;
