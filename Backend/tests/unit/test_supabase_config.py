"""Unit tests for Supabase config key alias logic."""


_BASE_SETTINGS = dict(
    SECRET_KEY="a" * 40,
    ENCRYPTION_KEY="ScMKcnTeUAIxkeKkhFe-n7BTVisJRW2qpeNc3vqdah0=",
    SUPABASE_URL="https://test.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY="svc",
    DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
    REDIS_URL="redis://localhost/0",
    CLOUDFLARE_ACCOUNT_ID="acc",
    CLOUDFLARE_R2_BUCKET="bucket",
    CLOUDFLARE_R2_ACCESS_KEY="key",
    CLOUDFLARE_R2_SECRET_KEY="sec",
    CLOUDFLARE_R2_PUBLIC_URL="https://cdn.example.com",
    CLOUDFLARE_R2_ENDPOINT="https://acc.r2.cloudflarestorage.com",
    RESEND_API_KEY="re_test",
    EMAIL_FROM="n@test.com",
    EMAIL_REPLY_TO="s@test.com",
    RAZORPAY_KEY_ID="rzp_k",
    RAZORPAY_KEY_SECRET="rzp_s",
    RAZORPAY_WEBHOOK_SECRET="rzp_w",
    DELIVERY_ONE_BASE_URL="https://api.do.test",
    DELIVERY_ONE_API_KEY="do_key",
    DELIVERY_ONE_WEBHOOK_SECRET="do_ws",
    FRONTEND_URL="http://localhost:3000",
    ADMIN_URL="http://localhost:3001",
)


class TestSupabaseKeyAlias:
    """SUPABASE_KEY (new format) and SUPABASE_ANON_KEY (legacy) are interchangeable."""

    def test_supabase_key_takes_precedence(self):
        from app.core.config import Settings
        s = Settings(
            **_BASE_SETTINGS,
            SUPABASE_KEY="sb_publishable_newkey",
            SUPABASE_ANON_KEY="old_anon_key",
        )
        assert s.supabase_anon_key == "sb_publishable_newkey"

    def test_legacy_anon_key_fallback(self):
        from app.core.config import Settings
        s = Settings(
            **_BASE_SETTINGS,
            SUPABASE_KEY="",
            SUPABASE_ANON_KEY="legacy_anon_key",
        )
        assert s.supabase_anon_key == "legacy_anon_key"

    def test_both_empty_returns_empty(self):
        from app.core.config import Settings
        s = Settings(
            **_BASE_SETTINGS,
            SUPABASE_KEY="",
            SUPABASE_ANON_KEY="",
        )
        assert s.supabase_anon_key == ""
