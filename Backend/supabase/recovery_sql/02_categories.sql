-- ============================================================
-- 02_categories.sql
-- Category tree restoration, recovered from the Redis cache key
-- `categories:tree:v1:all` (decoded payload:
-- recovery-backup/Json data/categories_tree.json).
-- Cache write timestamp (epoch): 1784981523.2137246
--
-- SCOPE: `categories` table ONLY. Navigation/navbar caches are just
-- alternate projections of these same rows (cross-verified in the
-- recovery report) and need no separate restoration.
--
-- Every id below is a REAL recovered production UUID (category ids survive
-- directly in the cache, unlike homepage section ids) - ON CONFLICT (id) is
-- the correct, non-fabricated upsert target throughout.
--
-- NOT restored: image_url (not a categories column - resolved via a
-- polymorphic join to images/image_variants at read time; those tables'
-- required NOT NULL fields did not survive in the cache - see the
-- recovery report). product_count is also not a column (computed live).
--
-- Idempotent: INSERT ... ON CONFLICT DO UPDATE only. No DELETE/TRUNCATE.
-- Rows are ordered parent-before-child so the self-referencing
-- categories.parent_id FK never fails mid-script.
-- ============================================================

BEGIN;

-- shop-women  (id = 2bde3046-a123-4197-99be-9cc11439ec35 - top-level)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('2bde3046-a123-4197-99be-9cc11439ec35', NULL, 'Shop Women', 'shop-women', 10, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-lockets  (id = 61d873f9-00e0-4f34-b3f5-cd63011a437d, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('61d873f9-00e0-4f34-b3f5-cd63011a437d', '2bde3046-a123-4197-99be-9cc11439ec35', 'Lockets', 'women-lockets', 10, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-rings  (id = 0515966d-9d60-433b-bca7-aace9db0ce8b, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('0515966d-9d60-433b-bca7-aace9db0ce8b', '2bde3046-a123-4197-99be-9cc11439ec35', 'Rings', 'women-rings', 20, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-stud-earrings  (id = c6c0db91-783c-4e1e-bafb-48e715ef65da, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('c6c0db91-783c-4e1e-bafb-48e715ef65da', '2bde3046-a123-4197-99be-9cc11439ec35', 'Stud Earrings', 'women-stud-earrings', 30, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-jhumkas  (id = 42dcf8d4-b2bd-4300-9d68-00ecb51d6ce8, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('42dcf8d4-b2bd-4300-9d68-00ecb51d6ce8', '2bde3046-a123-4197-99be-9cc11439ec35', 'Jhumkas', 'women-jhumkas', 40, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-long-earrings  (id = 76e25fa1-9671-4435-bfb0-aa77c0659e70, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('76e25fa1-9671-4435-bfb0-aa77c0659e70', '2bde3046-a123-4197-99be-9cc11439ec35', 'Long Earrings', 'women-long-earrings', 50, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-short-earrings  (id = 282a8c32-a5c2-492e-9db4-409d5db4f171, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('282a8c32-a5c2-492e-9db4-409d5db4f171', '2bde3046-a123-4197-99be-9cc11439ec35', 'Short Earrings', 'women-short-earrings', 60, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-bracelets  (id = 46904638-25e0-4c0f-a3c1-622adf82bf4f, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('46904638-25e0-4c0f-a3c1-622adf82bf4f', '2bde3046-a123-4197-99be-9cc11439ec35', 'Bracelets', 'women-bracelets', 70, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-chain-locket-sets  (id = c2276836-a5dd-4be7-8b9b-a72c7dadb8b1, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('c2276836-a5dd-4be7-8b9b-a72c7dadb8b1', '2bde3046-a123-4197-99be-9cc11439ec35', 'Chain & Locket Sets', 'women-chain-locket-sets', 90, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-toe-rings  (id = a4578f48-166f-4722-829d-16501fb41730, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('a4578f48-166f-4722-829d-16501fb41730', '2bde3046-a123-4197-99be-9cc11439ec35', 'Toe Rings', 'women-toe-rings', 100, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- women-bangles  (id = f2274295-cb17-4eea-9b39-e7c8cc953cbc, parent = 2bde3046-a123-4197-99be-9cc11439ec35)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('f2274295-cb17-4eea-9b39-e7c8cc953cbc', '2bde3046-a123-4197-99be-9cc11439ec35', 'Bangles', 'women-bangles', 110, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- shop-men  (id = 020c8125-494f-4a2b-8bc7-e6eefe912ca2 - top-level)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('020c8125-494f-4a2b-8bc7-e6eefe912ca2', NULL, 'Shop Men', 'shop-men', 20, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- men-lockets  (id = 6754114b-99f7-4738-a746-714f768d54a0, parent = 020c8125-494f-4a2b-8bc7-e6eefe912ca2)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('6754114b-99f7-4738-a746-714f768d54a0', '020c8125-494f-4a2b-8bc7-e6eefe912ca2', 'Lockets', 'men-lockets', 10, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- men-rings  (id = 765f7a8c-83e0-4c54-a35e-4b62979c8112, parent = 020c8125-494f-4a2b-8bc7-e6eefe912ca2)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('765f7a8c-83e0-4c54-a35e-4b62979c8112', '020c8125-494f-4a2b-8bc7-e6eefe912ca2', 'Rings', 'men-rings', 20, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- men-bracelets  (id = ae62bcc2-28fd-4d21-be3c-ce37220edce0, parent = 020c8125-494f-4a2b-8bc7-e6eefe912ca2)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('ae62bcc2-28fd-4d21-be3c-ce37220edce0', '020c8125-494f-4a2b-8bc7-e6eefe912ca2', 'Bracelets', 'men-bracelets', 30, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- men-chains  (id = 366f4b85-944b-427f-8ff7-e0c02eefdcd5, parent = 020c8125-494f-4a2b-8bc7-e6eefe912ca2)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('366f4b85-944b-427f-8ff7-e0c02eefdcd5', '020c8125-494f-4a2b-8bc7-e6eefe912ca2', 'Chains', 'men-chains', 40, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- shop-unisex  (id = 8f6fce03-52fb-4c0b-96c9-0eff9cd63aac - top-level)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('8f6fce03-52fb-4c0b-96c9-0eff9cd63aac', NULL, 'Unisex', 'shop-unisex', 25, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- ear-studs  (id = 68bfd47d-7b18-454e-9edd-943bb5c34fca, parent = 8f6fce03-52fb-4c0b-96c9-0eff9cd63aac)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('68bfd47d-7b18-454e-9edd-943bb5c34fca', '8f6fce03-52fb-4c0b-96c9-0eff9cd63aac', 'ear studs', 'ear-studs', 0, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- eliphant-ring  (id = aa4db18e-0819-40e6-a2f7-1818ea5f53b2, parent = 8f6fce03-52fb-4c0b-96c9-0eff9cd63aac)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('aa4db18e-0819-40e6-a2f7-1818ea5f53b2', '8f6fce03-52fb-4c0b-96c9-0eff9cd63aac', 'Eliphant Ring', 'eliphant-ring', 0, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- unisex-lockets  (id = 5123d7d3-c75e-41b9-b049-99a533560167, parent = 8f6fce03-52fb-4c0b-96c9-0eff9cd63aac)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('5123d7d3-c75e-41b9-b049-99a533560167', '8f6fce03-52fb-4c0b-96c9-0eff9cd63aac', 'Lockets', 'unisex-lockets', 10, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- couple-rings  (id = cc6d9634-f15c-47d2-bebf-f9001f70eb22, parent = 8f6fce03-52fb-4c0b-96c9-0eff9cd63aac)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('cc6d9634-f15c-47d2-bebf-f9001f70eb22', '8f6fce03-52fb-4c0b-96c9-0eff9cd63aac', 'Couple Rings', 'couple-rings', 40, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- shop-kids  (id = 1de28621-0acb-4bca-ba08-a01f38610bd4 - top-level)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('1de28621-0acb-4bca-ba08-a01f38610bd4', NULL, 'Kids', 'shop-kids', 30, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- kids-earrings  (id = 7ab5330b-2132-4001-b8f3-8658c456a3c5, parent = 1de28621-0acb-4bca-ba08-a01f38610bd4)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('7ab5330b-2132-4001-b8f3-8658c456a3c5', '1de28621-0acb-4bca-ba08-a01f38610bd4', 'Earrings', 'kids-earrings', 10, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- kids-bangles  (id = da3677ad-0fac-4750-9966-06f51657ad3c, parent = 1de28621-0acb-4bca-ba08-a01f38610bd4)
INSERT INTO categories
    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)
VALUES
    ('da3677ad-0fac-4750-9966-06f51657ad3c', '1de28621-0acb-4bca-ba08-a01f38610bd4', 'Bangles', 'kids-bangles', 20, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- ── Validation ───────────────────────────────────────────────────────────
DO $$
DECLARE
    cat_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO cat_count FROM categories WHERE id IN (
        '2bde3046-a123-4197-99be-9cc11439ec35', '61d873f9-00e0-4f34-b3f5-cd63011a437d', '0515966d-9d60-433b-bca7-aace9db0ce8b', 'c6c0db91-783c-4e1e-bafb-48e715ef65da', '42dcf8d4-b2bd-4300-9d68-00ecb51d6ce8', '76e25fa1-9671-4435-bfb0-aa77c0659e70', '282a8c32-a5c2-492e-9db4-409d5db4f171', '46904638-25e0-4c0f-a3c1-622adf82bf4f', 'c2276836-a5dd-4be7-8b9b-a72c7dadb8b1', 'a4578f48-166f-4722-829d-16501fb41730', 'f2274295-cb17-4eea-9b39-e7c8cc953cbc', '020c8125-494f-4a2b-8bc7-e6eefe912ca2', '6754114b-99f7-4738-a746-714f768d54a0', '765f7a8c-83e0-4c54-a35e-4b62979c8112', 'ae62bcc2-28fd-4d21-be3c-ce37220edce0', '366f4b85-944b-427f-8ff7-e0c02eefdcd5', '8f6fce03-52fb-4c0b-96c9-0eff9cd63aac', '68bfd47d-7b18-454e-9edd-943bb5c34fca', 'aa4db18e-0819-40e6-a2f7-1818ea5f53b2', '5123d7d3-c75e-41b9-b049-99a533560167', 'cc6d9634-f15c-47d2-bebf-f9001f70eb22', '1de28621-0acb-4bca-ba08-a01f38610bd4', '7ab5330b-2132-4001-b8f3-8658c456a3c5', 'da3677ad-0fac-4750-9966-06f51657ad3c');
    IF cat_count <> 24 THEN
        RAISE EXCEPTION 'category restore validation failed: expected 24 rows, found %', cat_count;
    END IF;
    RAISE NOTICE 'Category tree restore validated: % of 24 recovered categories present', cat_count;
END $$;

COMMIT;
