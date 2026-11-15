"""Self-hosted auth: credentials, OAuth identities, sessions, one-time tokens.

Replaces Supabase Auth with first-party auth (HttpOnly-cookie sessions).

  1. New tables (RLS enabled, no policies — the backend owner role bypasses it):
       user_credentials   bcrypt password hash + email verification, 1:1 with profiles
       oauth_identities   Google (provider, subject) -> profile
       auth_sessions      one row per login; rotating hashed refresh token
       auth_tokens        hashed one-time email-verify / password-reset tokens
  2. One-time import from ``auth.users`` / ``auth.identities`` (skipped when the
     ``auth`` schema does not exist). Supabase stores bcrypt ``$2a$`` hashes, which
     the new login verifies unchanged, so every user keeps their password. Google
     users are linked by their Google ``sub``. Re-runnable: ON CONFLICT DO NOTHING.
  3. Cuts every tie from ``public`` to Supabase so the schema is a plain-Postgres
     schema (``pg_dump -n public`` restores anywhere):
       * ``profiles_id_fkey`` -> auth.users(id)
       * ``on_auth_user_created`` trigger + ``handle_new_user()``
       * every RLS policy that references ``auth.*`` (the app never used them —
         it connects as the table owner)

Data-safe: no existing row in ``public`` is modified or deleted. The dropped
policies are not restored by downgrade (they call ``auth.uid()``, which does not
exist off Supabase); supabase/sql/021_rls.sql still holds their definitions.
The trigger drop is best-effort: if the migration role does not own
``auth.users`` the trigger is left in place (it is inert once Supabase Auth is
no longer inserting users) and a warning is raised.

Revision ID: 0070_self_auth
Revises: 0069_reviews_open_posting
Create Date: 2026-11-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0070_self_auth"
down_revision: str | None = "0069_reviews_open_posting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE_CREDENTIALS = """
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    password_hash TEXT,
    email_verified_at TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_IDENTITIES = """
CREATE TABLE IF NOT EXISTS oauth_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    provider VARCHAR(32) NOT NULL,
    provider_subject VARCHAR(255) NOT NULL,
    email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    CONSTRAINT uq_oauth_identity_provider_subject UNIQUE (provider, provider_subject)
)
"""

_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    refresh_hash CHAR(64) NOT NULL,
    prev_refresh_hash CHAR(64),
    rotated_at TIMESTAMPTZ,
    surface VARCHAR(10) NOT NULL DEFAULT 'store',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT uq_auth_sessions_refresh_hash UNIQUE (refresh_hash)
)
"""

_CREATE_TOKENS = """
CREATE TABLE IF NOT EXISTS auth_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    purpose VARCHAR(20) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    binder_hash CHAR(64),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_auth_tokens_token_hash UNIQUE (token_hash),
    CONSTRAINT ck_auth_tokens_purpose
        CHECK (purpose IN ('email_verify', 'password_reset'))
)
"""

_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_oauth_identities_user ON oauth_identities (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_active "
    "ON auth_sessions (user_id) WHERE revoked_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_prev_hash "
    "ON auth_sessions (prev_refresh_hash) WHERE prev_refresh_hash IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_purpose "
    "ON auth_tokens (user_id, purpose)",
    "CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires ON auth_tokens (expires_at)",
)

_NEW_TABLES = ("user_credentials", "oauth_identities", "auth_sessions", "auth_tokens")

# Defence in depth on Supabase: even with the Data API closed (0067), a new
# table must not be reachable by anon/authenticated. These hold password
# hashes, so RLS is enabled with no policy and the roles' grants are revoked.
_LOCK_DOWN = r"""
DO $lock$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['user_credentials', 'oauth_identities', 'auth_sessions', 'auth_tokens']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('anon', 'authenticated')) THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
        END IF;
    END LOOP;
END
$lock$
"""

_IMPORT_CREDENTIALS = r"""
DO $imp$
BEGIN
    IF to_regclass('auth.users') IS NOT NULL THEN
        INSERT INTO public.user_credentials
            (user_id, password_hash, email_verified_at, created_at, updated_at)
        SELECT u.id,
               NULLIF(u.encrypted_password, ''),
               u.email_confirmed_at,
               COALESCE(u.created_at, now()),
               now()
        FROM auth.users u
        JOIN public.profiles p ON p.id = u.id
        WHERE u.deleted_at IS NULL
        ON CONFLICT (user_id) DO NOTHING;
    END IF;
END
$imp$
"""

_IMPORT_IDENTITIES = r"""
DO $imp$
BEGIN
    IF to_regclass('auth.identities') IS NOT NULL THEN
        INSERT INTO public.oauth_identities
            (user_id, provider, provider_subject, email, created_at, last_login_at)
        SELECT i.user_id,
               'google',
               COALESCE(i.identity_data->>'sub', i.provider_id),
               lower(i.identity_data->>'email'),
               COALESCE(i.created_at, now()),
               i.last_sign_in_at
        FROM auth.identities i
        JOIN public.profiles p ON p.id = i.user_id
        WHERE i.provider = 'google'
        ON CONFLICT (provider, provider_subject) DO NOTHING;
    END IF;
END
$imp$
"""

_DROP_PROFILE_FK = "ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_id_fkey"

_DROP_SIGNUP_TRIGGER = r"""
DO $trg$
BEGIN
    IF to_regclass('auth.users') IS NOT NULL THEN
        BEGIN
            DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
            DROP FUNCTION IF EXISTS public.handle_new_user();
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE WARNING 'on_auth_user_created not dropped: migration role does not own auth.users';
        END;
    ELSE
        DROP FUNCTION IF EXISTS public.handle_new_user();
    END IF;
END
$trg$
"""

_DROP_AUTH_POLICIES = r"""
DO $pol$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT schemaname, tablename, policyname
        FROM pg_policies
        WHERE schemaname = 'public'
          AND (qual ~* '\mauth\.[a-z_]+\s*\(' OR with_check ~* '\mauth\.[a-z_]+\s*\(')
    LOOP
        EXECUTE format('DROP POLICY %I ON %I.%I', r.policyname, r.schemaname, r.tablename);
    END LOOP;
END
$pol$
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    for stmt in (
        _CREATE_CREDENTIALS,
        _CREATE_IDENTITIES,
        _CREATE_SESSIONS,
        _CREATE_TOKENS,
        *_INDEXES,
        _LOCK_DOWN,
        _IMPORT_CREDENTIALS,
        _IMPORT_IDENTITIES,
        _DROP_PROFILE_FK,
        _DROP_SIGNUP_TRIGGER,
        _DROP_AUTH_POLICIES,
    ):
        op.execute(stmt)


def downgrade() -> None:
    # Only the new tables go; the dropped Supabase ties are intentionally not
    # restored (see module docstring). Sessions and tokens are disposable;
    # credentials/identities can be re-imported from auth.users if it still exists.
    for table in reversed(_NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
