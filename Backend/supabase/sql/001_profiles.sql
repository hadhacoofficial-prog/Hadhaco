-- ============================================================
-- 001_profiles.sql
-- Tables: profiles, admin_2fa, admin_sessions
-- Trigger: auto-create profile on auth.users insert
-- ============================================================

-- ── profiles ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.profiles (
    id           UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email        TEXT NOT NULL UNIQUE,
    full_name    TEXT,
    phone        TEXT CHECK (phone ~ '^\+[1-9]\d{7,14}$' OR phone IS NULL),
    avatar_url   TEXT,
    role         TEXT NOT NULL DEFAULT 'customer'
                     CHECK (role IN ('customer', 'admin', 'super_admin')),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_email  ON public.profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_role   ON public.profiles(role);
CREATE INDEX IF NOT EXISTS idx_profiles_active ON public.profiles(is_active)
    WHERE is_active = TRUE;

-- ── admin_2fa ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.admin_2fa (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
    totp_secret  TEXT NOT NULL,               -- encrypted via Fernet (app-level)
    backup_codes JSONB NOT NULL DEFAULT '[]', -- array of bcrypt-hashed backup codes
    is_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    enabled_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── admin_sessions ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.admin_sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    ip_address   INET NOT NULL,
    user_agent   TEXT,
    device_hash  TEXT,
    location     JSONB,                        -- {country, city, region}
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_sessions_user_id ON public.admin_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_ip      ON public.admin_sessions(ip_address);

-- NOTE: audit_logs lives in 013_audit_logs.sql (partitioned by month).

-- ── Auto-create profile trigger ───────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, avatar_url, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        NEW.raw_user_meta_data->>'avatar_url',
        'customer'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- ── updated_at auto-update trigger (reusable) ─────────────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_admin_2fa_updated_at ON public.admin_2fa;
CREATE TRIGGER trg_admin_2fa_updated_at
    BEFORE UPDATE ON public.admin_2fa
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── RLS policies ─────────────────────────────────────────────────────────────
ALTER TABLE public.profiles     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_2fa    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_sessions ENABLE ROW LEVEL SECURITY;

-- Profiles: users can read/update only their own row
DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
CREATE POLICY "profiles_select_own" ON public.profiles FOR SELECT
    USING (auth.uid() = id);

DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
CREATE POLICY "profiles_update_own" ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

-- Admins (via service role) bypass RLS — FastAPI backend uses service role key
-- Frontend anon key is never used for direct DB access to these tables

-- admin_2fa: user can only see their own
DROP POLICY IF EXISTS "admin_2fa_own" ON public.admin_2fa;
CREATE POLICY "admin_2fa_own" ON public.admin_2fa FOR ALL
    USING (auth.uid() = user_id);

-- admin_sessions: user can only see their own
DROP POLICY IF EXISTS "admin_sessions_own" ON public.admin_sessions;
CREATE POLICY "admin_sessions_own" ON public.admin_sessions FOR ALL
    USING (auth.uid() = user_id);

-- audit_logs RLS lives in 021_rls.sql (table created in 013).
