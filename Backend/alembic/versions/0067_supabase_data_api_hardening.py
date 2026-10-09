"""Close Supabase Data API (PostgREST) exposure of the application schema.

The FastAPI backend talks to Postgres with its own (owner / BYPASSRLS) role and
never uses the Data API tables from the browser, so the ``anon`` and
``authenticated`` roles need no privileges on ``public`` at all. Historically
they were left with Supabase's default grants, which combined with the
owner-writable policies in supabase/sql/001_profiles.sql allowed:

  * a customer to UPDATE their own ``profiles.role`` (self-promotion to
    super_admin) through the public anon key,
  * an admin token to read/forge ``admin_2fa`` secrets and ``admin_sessions``
    rows,
  * plain views (``order_detail_view`` ...) to bypass row-level security and
    expose customer PII,
  * any table created by Alembic (no ENABLE ROW LEVEL SECURITY) to be exposed.

This migration is data-safe and re-runnable: it changes privileges/RLS flags and
adds a trigger only — no rows are read, modified or deleted — and it is a no-op
on databases without the Supabase ``anon``/``authenticated`` roles (plain
Postgres / CI).

  1. views run with the caller's privileges (security_invoker, PG15+);
  2. ``anon`` / ``authenticated`` lose every privilege on public tables, views
     and sequences, and future objects are not granted to them by default;
  3. row level security is enabled on every public table that is missing it
     (owner role keeps bypassing it, so the backend is unaffected);
  4. defence in depth: a trigger blocks ``anon``/``authenticated`` from ever
     changing ``profiles.role`` / ``profiles.is_active``, even if a grant or
     policy is re-introduced later.

Downgrade removes only the trigger; previously-held grants are intentionally not
restored (they were the vulnerability, and their prior state is unknown).

Revision ID: 0067_supabase_data_api_hardening
Revises: 0066_list_sort_filter_indexes
Create Date: 2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0067_supabase_data_api_hardening"
down_revision: str | None = "0066_list_sort_filter_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HARDEN = r"""
DO $hardening$
DECLARE
    r record;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('anon', 'authenticated')) THEN
        RAISE NOTICE 'Supabase Data API roles not present; skipping hardening';
        RETURN;
    END IF;

    -- 1. Views must evaluate with the caller's privileges / RLS.
    IF current_setting('server_version_num')::int >= 150000 THEN
        FOR r IN
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'v'
              AND pg_has_role(current_user, c.relowner, 'MEMBER')
        LOOP
            EXECUTE format('ALTER VIEW public.%I SET (security_invoker = true)', r.relname);
        END LOOP;
    END IF;

    -- 2. The browser-facing roles get nothing in the application schema.
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated';

    -- 3. RLS on every public table that lacks it (owner keeps bypassing RLS).
    FOR r IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
          AND NOT c.relrowsecurity
          AND c.relname <> 'alembic_version'
          AND pg_has_role(current_user, c.relowner, 'MEMBER')
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.relname);
    END LOOP;
END
$hardening$
"""

# 4. Defence in depth: privileged profile columns are service-only.
_PROTECT_FN = r"""
CREATE OR REPLACE FUNCTION public.protect_profile_privileged_columns()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $fn$
BEGIN
    IF current_user IN ('anon', 'authenticated')
       AND (NEW.role IS DISTINCT FROM OLD.role
            OR NEW.is_active IS DISTINCT FROM OLD.is_active) THEN
        RAISE EXCEPTION 'profiles.role and profiles.is_active can only be changed by the service'
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END
$fn$
"""

_PROTECT_TRG = r"""
DO $trg$
BEGIN
    IF to_regclass('public.profiles') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS trg_protect_profile_privileged_columns ON public.profiles;
        CREATE TRIGGER trg_protect_profile_privileged_columns
            BEFORE UPDATE ON public.profiles
            FOR EACH ROW EXECUTE FUNCTION public.protect_profile_privileged_columns();
    END IF;
END
$trg$
"""

# One statement per execute(): asyncpg cannot run multiple commands in a
# single prepared statement.
UPGRADE_STATEMENTS: tuple[str, ...] = (_HARDEN, _PROTECT_FN, _PROTECT_TRG)
DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "DROP TRIGGER IF EXISTS trg_protect_profile_privileged_columns "
    "ON public.profiles",
    "DROP FUNCTION IF EXISTS public.protect_profile_privileged_columns()",
)


def upgrade() -> None:
    for stmt in UPGRADE_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # to_regclass guard not needed: DROP ... IF EXISTS on a missing table errors
    # only for the table, so check it first.
    op.execute(
        "DO $d$ BEGIN IF to_regclass('public.profiles') IS NOT NULL THEN "
        "DROP TRIGGER IF EXISTS trg_protect_profile_privileged_columns "
        "ON public.profiles; END IF; END $d$"
    )
    op.execute(DOWNGRADE_STATEMENTS[1])
