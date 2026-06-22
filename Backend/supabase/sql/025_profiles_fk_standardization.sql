-- ============================================================
-- 025_profiles_fk_standardization.sql
-- One-time migration for EXISTING databases.
--
-- Repoints every business-table foreign key that targets auth.users(id)
-- to public.profiles(id), making profiles the single source of truth for
-- application user data. profiles.id == auth.users.id (1:1, kept in sync by
-- the handle_new_user trigger), so NO data migration is required and NO data
-- is dropped — only the FK constraint target changes.
--
-- After this runs, ONLY public.profiles references auth.users.
--
-- Safe to run exactly once via the Supabase SQL Editor. It is also idempotent:
-- re-running is a no-op because the repoint is skipped once the FK already
-- points at profiles. Fresh databases built from setup.sql already reference
-- profiles directly and do not need this file.
--
-- NOTE: admin_2fa and admin_sessions already reference public.profiles and are
-- intentionally not touched. analytics_events / notifications / fraud_* keep
-- their nullable, FK-less user_id columns (anonymous & system events) — they
-- never referenced auth.users, so there is nothing to repoint.
-- ============================================================

BEGIN;

-- Helper: drop any FK on (table, column) that points at auth.users, then add
-- an equivalent FK to public.profiles with the requested ON DELETE rule.
-- Created in pg_temp so it is dropped automatically at session end.
CREATE OR REPLACE FUNCTION pg_temp.repoint_to_profiles(
    p_table     text,
    p_column    text,
    p_on_delete text
) RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_con  text;
    v_name text := format('%s_%s_fkey', p_table, p_column);
BEGIN
    -- Drop every existing single-column FK on p_table.p_column -> auth.users.
    FOR v_con IN
        SELECT con.conname
        FROM   pg_constraint con
        JOIN   pg_class      rel  ON rel.oid  = con.conrelid
        JOIN   pg_namespace  nsp  ON nsp.oid  = rel.relnamespace
        JOIN   pg_class      frel ON frel.oid = con.confrelid
        JOIN   pg_namespace  fnsp ON fnsp.oid = frel.relnamespace
        WHERE  con.contype = 'f'
          AND  nsp.nspname  = 'public'
          AND  rel.relname  = p_table
          AND  fnsp.nspname = 'auth'
          AND  frel.relname = 'users'
          AND  array_length(con.conkey, 1) = 1
          AND  (SELECT attname FROM pg_attribute
                WHERE attrelid = con.conrelid AND attnum = con.conkey[1]) = p_column
    LOOP
        EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT %I', p_table, v_con);
    END LOOP;

    -- Add the FK to profiles only if one does not already exist.
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint con
        JOIN   pg_class      rel  ON rel.oid  = con.conrelid
        JOIN   pg_namespace  nsp  ON nsp.oid  = rel.relnamespace
        JOIN   pg_class      frel ON frel.oid = con.confrelid
        JOIN   pg_namespace  fnsp ON fnsp.oid = frel.relnamespace
        WHERE  con.contype = 'f'
          AND  nsp.nspname  = 'public'
          AND  rel.relname  = p_table
          AND  fnsp.nspname = 'public'
          AND  frel.relname = 'profiles'
          AND  array_length(con.conkey, 1) = 1
          AND  (SELECT attname FROM pg_attribute
                WHERE attrelid = con.conrelid AND attnum = con.conkey[1]) = p_column
    ) THEN
        EXECUTE format(
            'ALTER TABLE public.%I ADD CONSTRAINT %I '
            'FOREIGN KEY (%I) REFERENCES public.profiles(id) ON DELETE %s',
            p_table, v_name, p_column, p_on_delete
        );
    END IF;
END;
$fn$;

-- Repoint every FK (cascade rules preserved from the original schema).
SELECT pg_temp.repoint_to_profiles('user_addresses',      'user_id',    'CASCADE');
SELECT pg_temp.repoint_to_profiles('wishlists',           'user_id',    'CASCADE');
SELECT pg_temp.repoint_to_profiles('carts',               'user_id',    'CASCADE');
SELECT pg_temp.repoint_to_profiles('orders',              'user_id',    'RESTRICT');
SELECT pg_temp.repoint_to_profiles('payments',            'user_id',    'RESTRICT');
SELECT pg_temp.repoint_to_profiles('reviews',             'user_id',    'CASCADE');
SELECT pg_temp.repoint_to_profiles('review_votes',        'user_id',    'CASCADE');
SELECT pg_temp.repoint_to_profiles('coupon_usages',       'user_id',    'CASCADE');
SELECT pg_temp.repoint_to_profiles('inventory_movements', 'created_by', 'SET NULL');

COMMIT;
