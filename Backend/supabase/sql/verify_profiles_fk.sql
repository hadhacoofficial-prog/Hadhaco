-- ============================================================
-- verify_profiles_fk.sql
-- Read-only verification for the profiles-as-single-source-of-truth refactor.
-- Run AFTER 025_profiles_fk_standardization.sql. Every query should return the
-- documented "expected" result. Safe to run anytime (no writes).
-- ============================================================

-- 1) The ONLY table allowed to reference auth.users is public.profiles.
--    Expected: exactly one row -> profiles.id -> users.id
SELECT nsp.nspname  AS table_schema,
       rel.relname  AS table_name,
       att.attname  AS column_name,
       con.conname  AS constraint_name
FROM   pg_constraint con
JOIN   pg_class      rel  ON rel.oid  = con.conrelid
JOIN   pg_namespace  nsp  ON nsp.oid  = rel.relnamespace
JOIN   pg_class      frel ON frel.oid = con.confrelid
JOIN   pg_namespace  fnsp ON fnsp.oid = frel.relnamespace
JOIN   pg_attribute  att  ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
WHERE  con.contype = 'f'
  AND  fnsp.nspname = 'auth'
  AND  frel.relname = 'users'
ORDER  BY nsp.nspname, rel.relname;
-- EXPECTED: 1 row -> public | profiles | id | profiles_id_fkey


-- 2) Every business FK that used to point at auth.users now points at profiles.
--    Expected: 9 rows (user_addresses, wishlists, carts, orders, payments,
--    reviews, review_votes, coupon_usages, inventory_movements).
SELECT rel.relname AS table_name,
       att.attname AS column_name,
       con.conname AS constraint_name,
       CASE con.confdeltype
            WHEN 'a' THEN 'NO ACTION'
            WHEN 'r' THEN 'RESTRICT'
            WHEN 'c' THEN 'CASCADE'
            WHEN 'n' THEN 'SET NULL'
            WHEN 'd' THEN 'SET DEFAULT'
       END         AS on_delete
FROM   pg_constraint con
JOIN   pg_class      rel  ON rel.oid  = con.conrelid
JOIN   pg_namespace  nsp  ON nsp.oid  = rel.relnamespace
JOIN   pg_class      frel ON frel.oid = con.confrelid
JOIN   pg_namespace  fnsp ON fnsp.oid = frel.relnamespace
JOIN   pg_attribute  att  ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
WHERE  con.contype = 'f'
  AND  fnsp.nspname = 'public'
  AND  frel.relname = 'profiles'
  AND  rel.relname  IN ('user_addresses','wishlists','carts','orders','payments',
                        'reviews','review_votes','coupon_usages','inventory_movements')
ORDER  BY rel.relname;
-- EXPECTED: 9 rows; on_delete matches: user_addresses/wishlists/carts/reviews/
-- review_votes/coupon_usages=CASCADE, orders/payments=RESTRICT,
-- inventory_movements=SET NULL


-- 3) No broken / orphaned FK values — every non-null user reference resolves to
--    a profiles row. Each query below must return 0.
SELECT 'user_addresses'      AS table_name, count(*) AS orphans FROM user_addresses      a LEFT JOIN profiles p ON p.id = a.user_id    WHERE a.user_id    IS NOT NULL AND p.id IS NULL
UNION ALL SELECT 'wishlists',           count(*) FROM wishlists           w LEFT JOIN profiles p ON p.id = w.user_id    WHERE w.user_id    IS NOT NULL AND p.id IS NULL
UNION ALL SELECT 'carts',               count(*) FROM carts               c LEFT JOIN profiles p ON p.id = c.user_id    WHERE c.user_id    IS NOT NULL AND p.id IS NULL
UNION ALL SELECT 'orders',              count(*) FROM orders              o LEFT JOIN profiles p ON p.id = o.user_id    WHERE o.user_id    IS NOT NULL AND p.id IS NULL
UNION ALL SELECT 'payments',            count(*) FROM payments            y LEFT JOIN profiles p ON p.id = y.user_id    WHERE y.user_id    IS NOT NULL AND p.id IS NULL
UNION ALL SELECT 'reviews',             count(*) FROM reviews             r LEFT JOIN profiles p ON p.id = r.user_id    WHERE r.user_id    IS NOT NULL AND p.id IS NULL
UNION ALL SELECT 'review_votes',        count(*) FROM review_votes        v LEFT JOIN profiles p ON p.id = v.user_id    WHERE v.user_id    IS NOT NULL AND p.id IS NULL
UNION ALL SELECT 'coupon_usages',       count(*) FROM coupon_usages       u LEFT JOIN profiles p ON p.id = u.user_id    WHERE u.user_id    IS NOT NULL AND p.id IS NULL
UNION ALL SELECT 'inventory_movements', count(*) FROM inventory_movements i LEFT JOIN profiles p ON p.id = i.created_by WHERE i.created_by IS NOT NULL AND p.id IS NULL;
-- EXPECTED: orphans = 0 for every row


-- 4) Confirm profiles is still a perfect 1:1 mirror of auth.users (sanity).
--    Expected: profiles_without_auth_user = 0
SELECT count(*) AS profiles_without_auth_user
FROM   public.profiles p
LEFT   JOIN auth.users u ON u.id = p.id
WHERE  u.id IS NULL;
-- EXPECTED: 0
