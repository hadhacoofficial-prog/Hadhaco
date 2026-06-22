-- ============================================================
-- 002_catalog.sql
-- Tables: categories, collections, product_collections,
--         products, product_variants, product_attributes,
--         product_images
-- Indexes, search_vector trigger
-- ============================================================

-- ── categories ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.categories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id       UUID REFERENCES public.categories(id),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    description     TEXT,
    image_url       TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    seo_title       TEXT,
    seo_description TEXT,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_categories_slug   ON public.categories(slug);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON public.categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_categories_active ON public.categories(is_active) WHERE is_active = TRUE;

-- ── collections ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.collections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    description     TEXT,
    image_url       TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_featured     BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    seo_title       TEXT,
    seo_description TEXT,
    starts_at       TIMESTAMPTZ,
    ends_at         TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_collections_slug     ON public.collections(slug);
CREATE INDEX IF NOT EXISTS idx_collections_active   ON public.collections(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_collections_featured ON public.collections(is_featured) WHERE is_featured = TRUE;

-- ── products ─────────────────────────────────────────────────────────────────
-- Schema matches app/modules/catalog/models.py (ORM is the source of truth).
CREATE TABLE IF NOT EXISTS public.products (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku                 VARCHAR(100) NOT NULL UNIQUE,
    name                VARCHAR(255) NOT NULL,
    slug                VARCHAR(255) NOT NULL UNIQUE,
    description         TEXT,
    short_description   VARCHAR(500),
    category_id         UUID REFERENCES public.categories(id) ON DELETE SET NULL,

    -- Jewellery-specific
    metal_type          VARCHAR(50),
    purity              VARCHAR(20),
    hallmark_number     VARCHAR(100),
    weight_grams        NUMERIC(10,3),
    making_charges      NUMERIC(12,2),
    wastage_percent     NUMERIC(5,2),
    gender              VARCHAR(20) CHECK (gender IS NULL OR gender IN ('women','men','kids','unisex')),

    -- Pricing (never expose cost_price to frontend)
    base_price          NUMERIC(12,2) NOT NULL CHECK (base_price > 0),
    compare_at_price    NUMERIC(12,2),
    cost_price          NUMERIC(12,2),
    tax_rate            NUMERIC(5,2) NOT NULL DEFAULT 3.0,
    hsn_code            VARCHAR(20),

    -- Inventory (stock lives on the product/variant rows; movements are the ledger)
    track_inventory     BOOLEAN NOT NULL DEFAULT TRUE,
    allow_backorder     BOOLEAN NOT NULL DEFAULT FALSE,
    low_stock_threshold INTEGER NOT NULL DEFAULT 5,
    stock_quantity      INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),

    -- Status / flags
    status              VARCHAR(20) NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft','active','archived')),
    is_featured         BOOLEAN NOT NULL DEFAULT FALSE,
    is_new_arrival      BOOLEAN NOT NULL DEFAULT FALSE,
    is_best_seller      BOOLEAN NOT NULL DEFAULT FALSE,
    is_customizable     BOOLEAN NOT NULL DEFAULT FALSE,
    requires_shipping   BOOLEAN NOT NULL DEFAULT TRUE,

    -- Dimensions (for shipping)
    length_cm           NUMERIC(8,2),
    width_cm            NUMERIC(8,2),
    height_cm           NUMERIC(8,2),

    -- SEO
    meta_title          VARCHAR(255),
    meta_description    VARCHAR(500),
    meta_keywords       VARCHAR(500),

    -- Full-text search vector (auto-updated via trigger)
    search_vector       TSVECTOR,

    -- Timestamps / soft delete
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at        TIMESTAMPTZ,
    deleted_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_products_slug        ON public.products(slug);
CREATE INDEX IF NOT EXISTS idx_products_sku         ON public.products(sku);
CREATE INDEX IF NOT EXISTS idx_products_category_id ON public.products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_status      ON public.products(status);
CREATE INDEX IF NOT EXISTS idx_products_is_featured ON public.products(is_featured) WHERE is_featured = TRUE;
CREATE INDEX IF NOT EXISTS idx_products_is_new      ON public.products(is_new_arrival) WHERE is_new_arrival = TRUE;
CREATE INDEX IF NOT EXISTS idx_products_metal_type  ON public.products(metal_type);
CREATE INDEX IF NOT EXISTS idx_products_gender      ON public.products(gender);
CREATE INDEX IF NOT EXISTS idx_products_price       ON public.products(base_price);
CREATE INDEX IF NOT EXISTS idx_products_search_vector ON public.products USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_products_deleted_at  ON public.products(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_products_created     ON public.products(created_at DESC);

-- ── product_collections (join) ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.product_collections (
    product_id    UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL REFERENCES public.collections(id) ON DELETE CASCADE,
    sort_order    INTEGER DEFAULT 0,
    PRIMARY KEY (product_id, collection_id)
);
CREATE INDEX IF NOT EXISTS idx_product_collections_col ON public.product_collections(collection_id);

-- ── product_variants ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.product_variants (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id       UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    sku              VARCHAR(100) NOT NULL UNIQUE,
    name             VARCHAR(255) NOT NULL,
    price_adjustment NUMERIC(12,2) NOT NULL DEFAULT 0,
    stock_quantity   INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    weight_grams     NUMERIC(10,3),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_product_variants_product_id ON public.product_variants(product_id);
CREATE INDEX IF NOT EXISTS idx_product_variants_sku        ON public.product_variants(sku);

-- ── product_attributes ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.product_attributes (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    name       VARCHAR(100) NOT NULL,
    value      VARCHAR(500) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_product_attributes_product_name UNIQUE (product_id, name)
);
CREATE INDEX IF NOT EXISTS idx_product_attributes_product_id ON public.product_attributes(product_id);

-- ── product_images ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.product_images (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id    UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    url           VARCHAR(1024) NOT NULL,
    thumbnail_url VARCHAR(1024),
    medium_url    VARCHAR(1024),
    alt_text      VARCHAR(255),
    is_primary    BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_product_images_product_id ON public.product_images(product_id, sort_order);

-- ── search_history ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.search_history (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES public.profiles(id),
    session_id   TEXT,
    query        TEXT NOT NULL,
    result_count INTEGER,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_search_history_user    ON public.search_history(user_id);
CREATE INDEX IF NOT EXISTS idx_search_history_query   ON public.search_history(query);
CREATE INDEX IF NOT EXISTS idx_search_history_created ON public.search_history(created_at DESC);

-- ── seo_pages ─────────────────────────────────────────────────────────────────
-- Path-keyed page metadata, matches app/modules/seo/service.py queries.
CREATE TABLE IF NOT EXISTS public.seo_pages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    path            TEXT NOT NULL UNIQUE,
    title           TEXT,
    description     TEXT,
    canonical_url   TEXT,
    og_image        TEXT,
    og_title        TEXT,
    og_description  TEXT,
    structured_data JSONB,
    noindex         BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_seo_pages_path ON public.seo_pages(path) WHERE is_active = TRUE;

-- ── seo_redirects ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.seo_redirects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_path   TEXT NOT NULL UNIQUE,
    to_path     TEXT NOT NULL,
    status_code INTEGER NOT NULL DEFAULT 301 CHECK (status_code IN (301, 302)),
    hit_count   INTEGER NOT NULL DEFAULT 0,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_seo_redirects_from ON public.seo_redirects(from_path) WHERE is_active = TRUE;

-- ── seo_404_log ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.seo_404_log (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    path       TEXT NOT NULL,
    referrer   TEXT,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_seo_404_path ON public.seo_404_log(path);

-- ── Search vector trigger ─────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.update_product_search_vector()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.name, '') || ' ' ||
        coalesce(NEW.short_description, '') || ' ' ||
        coalesce(NEW.description, '') || ' ' ||
        coalesce(NEW.metal_type, '') || ' ' ||
        coalesce(NEW.purity, '') || ' ' ||
        coalesce(NEW.meta_keywords, '')
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trgr_product_search_vector ON public.products;
CREATE TRIGGER trgr_product_search_vector
    BEFORE INSERT OR UPDATE ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.update_product_search_vector();

-- updated_at triggers
DROP TRIGGER IF EXISTS trg_categories_updated_at ON public.categories;
CREATE TRIGGER trg_categories_updated_at
    BEFORE UPDATE ON public.categories
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_collections_updated_at ON public.collections;
CREATE TRIGGER trg_collections_updated_at
    BEFORE UPDATE ON public.collections
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_products_updated_at ON public.products;
CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_product_variants_updated_at ON public.product_variants;
CREATE TRIGGER trg_product_variants_updated_at
    BEFORE UPDATE ON public.product_variants
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── Trending searches materialized view ──────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS public.trending_searches AS
SELECT query, COUNT(*) AS search_count
FROM public.search_history
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY query
ORDER BY search_count DESC
LIMIT 20;
CREATE UNIQUE INDEX IF NOT EXISTS idx_trending_searches ON public.trending_searches(query);

-- ── RLS ───────────────────────────────────────────────────────────────────────
ALTER TABLE public.categories       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.collections      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_images   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_attributes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_collections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.search_history   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seo_pages        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seo_redirects    ENABLE ROW LEVEL SECURITY;

-- Public read access for active catalog (frontend uses anon key)
DROP POLICY IF EXISTS "catalog_public_read" ON public.products;
CREATE POLICY "catalog_public_read" ON public.products FOR SELECT
    USING (status = 'active' AND deleted_at IS NULL);
DROP POLICY IF EXISTS "categories_public_read" ON public.categories;
CREATE POLICY "categories_public_read" ON public.categories FOR SELECT
    USING (is_active = TRUE AND deleted_at IS NULL);
DROP POLICY IF EXISTS "collections_public_read" ON public.collections;
CREATE POLICY "collections_public_read" ON public.collections FOR SELECT
    USING (is_active = TRUE AND deleted_at IS NULL);
DROP POLICY IF EXISTS "product_variants_public_read" ON public.product_variants;
CREATE POLICY "product_variants_public_read" ON public.product_variants FOR SELECT
    USING (is_active = TRUE);
DROP POLICY IF EXISTS "product_images_public_read" ON public.product_images;
CREATE POLICY "product_images_public_read" ON public.product_images FOR SELECT USING (TRUE);
DROP POLICY IF EXISTS "product_attributes_public_read" ON public.product_attributes;
CREATE POLICY "product_attributes_public_read" ON public.product_attributes FOR SELECT USING (TRUE);
DROP POLICY IF EXISTS "product_collections_public_read" ON public.product_collections;
CREATE POLICY "product_collections_public_read" ON public.product_collections FOR SELECT USING (TRUE);

-- Search history: own records only
DROP POLICY IF EXISTS "search_history_own" ON public.search_history;
CREATE POLICY "search_history_own" ON public.search_history FOR ALL
    USING (user_id = auth.uid() OR user_id IS NULL);

-- SEO: public read
DROP POLICY IF EXISTS "seo_pages_public_read" ON public.seo_pages;
CREATE POLICY "seo_pages_public_read" ON public.seo_pages FOR SELECT USING (TRUE);
DROP POLICY IF EXISTS "seo_redirects_public_read" ON public.seo_redirects;
CREATE POLICY "seo_redirects_public_read" ON public.seo_redirects FOR SELECT
    USING (is_active = TRUE);
