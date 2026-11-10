-- ============================================================
-- 008_reviews.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS reviews (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id              UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id                 UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_id                UUID REFERENCES orders(id) ON DELETE SET NULL,
    rating                  SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title                   VARCHAR(255),
    body                    TEXT,
    is_verified_purchase    BOOLEAN NOT NULL DEFAULT false,
    is_approved             BOOLEAN NOT NULL DEFAULT false,
    is_flagged              BOOLEAN NOT NULL DEFAULT false,
    helpful_count           INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at              TIMESTAMPTZ,
    UNIQUE (product_id, user_id)   -- one review per product per user
);

CREATE INDEX IF NOT EXISTS idx_reviews_product_id   ON reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user_id      ON reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_reviews_rating       ON reviews(rating);
CREATE INDEX IF NOT EXISTS idx_reviews_is_approved  ON reviews(is_approved);
CREATE INDEX IF NOT EXISTS idx_reviews_deleted_at   ON reviews(deleted_at);

DROP TRIGGER IF EXISTS set_reviews_updated_at ON reviews;
CREATE TRIGGER set_reviews_updated_at
    BEFORE UPDATE ON reviews
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Review images ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS review_images (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id   UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    r2_key      VARCHAR(512),
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_review_images_review_id ON review_images(review_id);

-- ── Helpful votes (one per user per review) ───────────────────────────────────

CREATE TABLE IF NOT EXISTS review_votes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id   UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    is_helpful  BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (review_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_review_votes_review_id ON review_votes(review_id);

-- ── Product rating summary view ───────────────────────────────────────────────

CREATE OR REPLACE VIEW product_rating_summary AS
    SELECT
        product_id,
        COUNT(*)                                        AS review_count,
        ROUND(AVG(rating)::NUMERIC, 1)                  AS average_rating,
        COUNT(*) FILTER (WHERE rating = 5)              AS five_star,
        COUNT(*) FILTER (WHERE rating = 4)              AS four_star,
        COUNT(*) FILTER (WHERE rating = 3)              AS three_star,
        COUNT(*) FILTER (WHERE rating = 2)              AS two_star,
        COUNT(*) FILTER (WHERE rating = 1)              AS one_star
    FROM reviews
    WHERE is_approved = true AND deleted_at IS NULL
    GROUP BY product_id;

-- ── RLS ───────────────────────────────────────────────────────────────────────

ALTER TABLE reviews      ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_votes  ENABLE ROW LEVEL SECURITY;

-- Anyone can read approved reviews
DROP POLICY IF EXISTS "reviews_public_read" ON reviews;
CREATE POLICY "reviews_public_read" ON reviews FOR SELECT
    USING (is_approved = true AND deleted_at IS NULL);

-- Owners can read their own (approved or pending)
DROP POLICY IF EXISTS "reviews_owner_read" ON reviews;
CREATE POLICY "reviews_owner_read" ON reviews FOR SELECT
    USING (user_id = auth.uid() AND deleted_at IS NULL);

-- Owners can insert/update their own
DROP POLICY IF EXISTS "reviews_owner_write" ON reviews;
CREATE POLICY "reviews_owner_write" ON reviews FOR INSERT
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "reviews_owner_update" ON reviews;
CREATE POLICY "reviews_owner_update" ON reviews FOR UPDATE
    USING (user_id = auth.uid() AND deleted_at IS NULL);

-- Review images: visible if review is visible
DROP POLICY IF EXISTS "review_images_public_read" ON review_images;
CREATE POLICY "review_images_public_read" ON review_images FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM reviews r
            WHERE r.id = review_images.review_id
            AND (r.is_approved = true OR r.user_id = auth.uid())
            AND r.deleted_at IS NULL
        )
    );

-- Votes: owners can read/write their own
DROP POLICY IF EXISTS "review_votes_owner_all" ON review_votes;
CREATE POLICY "review_votes_owner_all" ON review_votes FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
