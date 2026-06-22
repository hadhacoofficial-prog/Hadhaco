-- ============================================================
-- 010_cms.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS banners (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    banner_type         TEXT NOT NULL CHECK (banner_type IN ('hero','promo_strip','category_feature','popup')),
    title               TEXT,
    subtitle            TEXT,
    cta_text            TEXT,
    cta_url             TEXT,
    desktop_image_url   TEXT,
    mobile_image_url    TEXT,
    background_color    TEXT,
    text_color          TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    starts_at           TIMESTAMPTZ,
    ends_at             TIMESTAMPTZ,
    target_audience     TEXT DEFAULT 'all' CHECK (target_audience IN ('all','new_users','returning')),
    created_by          UUID REFERENCES profiles(id),
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_banners_active ON banners(banner_type, is_active, sort_order)
    WHERE is_active = TRUE AND deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS landing_sections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_key TEXT NOT NULL UNIQUE,
    title       TEXT,
    subtitle    TEXT,
    config      JSONB NOT NULL DEFAULT '{}',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_by  UUID REFERENCES profiles(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cms_pages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    seo_title       TEXT,
    seo_description TEXT,
    created_by      UUID REFERENCES profiles(id),
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cms_pages_slug ON cms_pages(slug) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    is_public   BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by  UUID REFERENCES profiles(id),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS set_banners_updated_at ON banners;
CREATE TRIGGER set_banners_updated_at
    BEFORE UPDATE ON banners
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS set_landing_sections_updated_at ON landing_sections;
CREATE TRIGGER set_landing_sections_updated_at
    BEFORE UPDATE ON landing_sections
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS set_cms_pages_updated_at ON cms_pages;
CREATE TRIGGER set_cms_pages_updated_at
    BEFORE UPDATE ON cms_pages
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
