-- ============================================================
-- 000_extensions.sql
-- Enable required PostgreSQL extensions.
-- Run once against the Supabase PostgreSQL instance.
-- ============================================================

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Cryptographic functions (used for TOTP secret encryption, backup code hashing)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Trigram indexes for full-text autocomplete / fuzzy search
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Accent-insensitive full-text search
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- GIN index support for composite types
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- ── Shared helper functions ───────────────────────────────────────────────────
-- Defined here because every subsequent table file attaches updated_at triggers.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;
