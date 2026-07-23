import sys
import warnings
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# razorpay 1.4.2 imports pkg_resources at module load time; upgrading to 2.x
# is a breaking change we haven't vetted for the payment flows, so silence
# this one known, third-party deprecation warning instead. config.py is the
# first app module main.py imports, well before anything (orders/service.py,
# payments/service.py) transitively imports razorpay during router setup.
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
    module=r"razorpay\.client",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── App ────────────────────────────────────────────────────────────────────
    APP_NAME: str = "Hadha.co"
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    LOG_SQL: bool = False  # echo SQL statements; never enable in production
    APP_VERSION: str = "1.0.0"
    ENABLE_DEV_AUTH: bool = False
    PROFILING_ENABLED: bool = True

    # ── API ────────────────────────────────────────────────────────────────────
    API_HOST: str = (
        "0.0.0.0"  # nosec B104 — intentional: container must bind all interfaces
    )
    API_PORT: int = 8000
    API_BASE_URL: str = "http://localhost:8000"
    API_V1_PREFIX: str = "/api/v1"

    # ── Security ───────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    # Comma-separated Fernet keys retired from active use but still needed to
    # decrypt data encrypted under them (e.g. existing Admin2FA.totp_secret
    # values). Safe key rotation: generate a new key, set it as
    # ENCRYPTION_KEY, move the *old* key here, deploy — decryption keeps
    # working for every existing value while all new/re-encrypted values use
    # the new key. Drop an old key from this list only once nothing still
    # depends on it (re-encrypt existing rows, or accept they age out).
    ENCRYPTION_KEY_LEGACY: str = ""
    ALLOWED_ORIGINS: str = (
        "http://localhost:8081,http://127.0.0.1:8081,http://localhost:3000,http://localhost:5173,http://localhost:8080,http://localhost:8081,http://www.localhost:3000,http://www.localhost:5173,http://www.localhost:8080,http://www.localhost:8081"
    )
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    # Extra IPs (beyond private/loopback ranges, which are always trusted) to
    # trust X-Real-IP/X-Forwarded-For from — e.g. a reverse proxy or load
    # balancer with a public IP. Comma-separated. Empty by default: private/
    # loopback peers cover the common Docker/internal-network deployment
    # without any configuration.
    TRUSTED_PROXY_IPS: str = ""

    # ── Supabase ───────────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str = ""  # legacy var name
    SUPABASE_KEY: str = ""  # publishable/anon key (new format: sb_publishable_*)
    SUPABASE_SERVICE_ROLE_KEY: str

    # ── JWT / JWKS ─────────────────────────────────────────────────────────────
    JWKS_CACHE_TTL: int = 600  # seconds between JWKS refreshes (10 minutes)

    @property
    def supabase_anon_key(self) -> str:
        """Return whichever of SUPABASE_KEY / SUPABASE_ANON_KEY is set."""
        return self.SUPABASE_KEY or self.SUPABASE_ANON_KEY

    @property
    def supabase_issuer(self) -> str:
        """JWT issuer claim issued by Supabase Auth."""
        return f"{self.SUPABASE_URL}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        """URL of the Supabase JWKS endpoint."""
        return f"{self.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

    # ── Database ───────────────────────────────────────────────────────────────
    # FastAPI runtime: must use postgresql+asyncpg:// (async, session pooler).
    DATABASE_URL: str

    # Alembic migrations: must use postgresql+psycopg:// (sync, direct connection).
    # Point at db.<project-ref>.supabase.co:5432 to bypass pgBouncer entirely —
    # this eliminates DuplicatePreparedStatementError and EMAXCONNSESSION issues.
    # If not set, Alembic falls back to DATABASE_URL with the driver swapped to psycopg.
    # See DEVOPS.md § "Database Connection Architecture".
    ALEMBIC_DATABASE_URL: str | None = None

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url_scheme(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the asyncpg driver (postgresql+asyncpg://). "
                "This is required for FastAPI's async SQLAlchemy runtime."
            )
        return v

    @field_validator("ALEMBIC_DATABASE_URL")
    @classmethod
    def validate_alembic_url_scheme(cls, v: str | None) -> str | None:
        if v and not v.startswith("postgresql+psycopg://"):
            raise ValueError(
                "ALEMBIC_DATABASE_URL must use the psycopg driver (postgresql+psycopg://). "
                "Set it to the Supabase Direct Connection URL."
            )
        return v

    # Supabase Session Pooler has a per-plan client cap (15 on the default plan).
    # Single shared engine for ALL components (API, workers, event listeners).
    # Budget: (pool_size + max_overflow) × uvicorn_workers ≤ supabase_limit − overhead
    # With 2 workers: (2 + 1) × 2 = 6 persistent connections, leaving 9 for
    # Alembic migrations, health checks, and transient session spikes.
    # Workers and event listeners reuse the same pool — no separate engine.
    DATABASE_POOL_SIZE: int = 2
    DATABASE_MAX_OVERFLOW: int = 1
    DATABASE_POOL_TIMEOUT: int = 30
    # Recycle idle connections after 30 minutes. Prevents stale TCP connections
    # from accumulating when traffic drops and the pool stays open but idle.
    DATABASE_POOL_RECYCLE: int = 1800

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str
    REDIS_CACHE_TTL: int = 300
    REDIS_RATE_LIMIT_TTL: int = 60

    # ── Cloudflare R2 ──────────────────────────────────────────────────────────
    CLOUDFLARE_ACCOUNT_ID: str
    CLOUDFLARE_R2_BUCKET: str
    CLOUDFLARE_R2_ACCESS_KEY: str
    CLOUDFLARE_R2_SECRET_KEY: str
    CLOUDFLARE_R2_PUBLIC_URL: str
    CLOUDFLARE_R2_ENDPOINT: str

    # ── Email ──────────────────────────────────────────────────────────────────
    RESEND_API_KEY: str
    EMAIL_FROM: str  # must be from a domain verified in your Resend dashboard
    EMAIL_REPLY_TO: str
    EMAIL_FROM_NAME: str = "Hadha.co"
    ADMIN_ALERT_EMAIL: str = "admin@hadha.co"

    # ── Brand identity (notification templates) ────────────────────────────────
    # All optional; defaults mirror the storefront's canonical BRAND config
    # (Frontend_whole/packages/shared-utils/src/config/brand.ts) so emails and
    # the site speak with one voice. CMS "footer" section config overrides
    # these at send time (see app/modules/notifications/branding.py).
    BRAND_NAME: str = "Hadha Silver Jewellery"
    BRAND_SHORT_NAME: str = "Hadha"
    BRAND_LEGAL_NAME: str = "Popula Dabba's Hadha"
    BRAND_TAGLINE: str = "92.5 Silver Jewellery"
    BRAND_DESCRIPTION: str = (
        "Popula Dabba's Hadha — handcrafted 92.5 silver jewellery rooted in "
        "South Indian heritage, made for everyday and treasured for a lifetime."
    )
    BRAND_LOGO_URL: str = ""
    BRAND_LOGO_DARK_URL: str = ""
    BRAND_ADDRESS: str = "MVP Sector 1, MVP Colony, Visakhapatnam 530017"
    SUPPORT_EMAIL: str = "hello@hadha.co"
    SUPPORT_PHONE: str = "+91 98765 43210"
    SOCIAL_INSTAGRAM_URL: str = "https://instagram.com/hadha"
    SOCIAL_FACEBOOK_URL: str = "https://facebook.com/hadha"
    SOCIAL_YOUTUBE_URL: str = "https://youtube.com/@hadha"

    # ── WhatsApp (Meta Business Cloud API) ─────────────────────────────────────
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_BUSINESS_PHONE: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_WEBHOOK_SECRET: str = ""
    WHATSAPP_API_VERSION: str = "v21.0"

    # ── Razorpay ───────────────────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str
    RAZORPAY_CURRENCY: str = "INR"

    # ── Frontend ──────────────────────────────────────────────────────────────
    FRONTEND_URL: str
    ADMIN_URL: str

    # ── Auth callbacks ────────────────────────────────────────────────────────
    SUPABASE_AUTH_REDIRECT_URL: str = "https://hadha.co/auth/callback"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # ── Rate limits ────────────────────────────────────────────────────────────
    RATE_LIMIT_AUTH: int = 10
    RATE_LIMIT_API: int = 200
    RATE_LIMIT_UPLOAD: int = 20
    RATE_LIMIT_WEBHOOK: int = 500

    # ── Worker / admin trigger settings ─────────────────────────────────────
    REVIEW_REMINDER_DELAY_HOURS: int = 48

    # ── Business settings ─────────────────────────────────────────────────────
    FREE_SHIPPING_THRESHOLD: int = 999
    SHIPPING_FLAT_RATE: int = 99
    TAX_RATE_GST: float = 3.0
    SELLER_STATE: str = "Maharashtra"
    SELLER_GSTIN: str = ""
    LOW_STOCK_THRESHOLD: int = 5
    ORDER_NUMBER_PREFIX: str = "HD"
    INVOICE_NUMBER_PREFIX: str = "INV"

    # ── Monitoring & Error Tracking ──────────────────────────────────────────
    SENTRY_DSN: str = ""  # GlitchTip/Sentry DSN for error tracking
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1  # 10% of transactions traced
    ENABLE_PROMETHEUS: bool = True  # expose /metrics for Prometheus scraping

    # ── Derived helpers ───────────────────────────────────────────────────────
    # R2 aliases — media/invoices services use the short names.
    @property
    def R2_ENDPOINT_URL(self) -> str:
        return self.CLOUDFLARE_R2_ENDPOINT

    @property
    def R2_ACCESS_KEY_ID(self) -> str:
        return self.CLOUDFLARE_R2_ACCESS_KEY

    @property
    def R2_SECRET_ACCESS_KEY(self) -> str:
        return self.CLOUDFLARE_R2_SECRET_KEY

    @property
    def R2_PUBLIC_URL(self) -> str:
        return self.CLOUDFLARE_R2_PUBLIC_URL

    @property
    def R2_BUCKET_NAME(self) -> str:
        return self.CLOUDFLARE_R2_BUCKET

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @property
    def trusted_proxy_ips_list(self) -> list[str]:
        return [ip.strip() for ip in self.TRUSTED_PROXY_IPS.split(",") if ip.strip()]

    @property
    def encryption_keys_list(self) -> list[str]:
        """Primary key first, then any retired keys — for MultiFernet."""
        legacy = [k.strip() for k in self.ENCRYPTION_KEY_LEGACY.split(",") if k.strip()]
        return [self.ENCRYPTION_KEY, *legacy]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "production"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}")
        return v


def validate_required_settings(s: Settings) -> None:
    """
    Called at startup. Raises SystemExit if any required setting is
    an empty string, listing every missing variable so the operator
    can fix them all at once.
    """
    required: list[tuple[str, str]] = [
        ("SECRET_KEY", s.SECRET_KEY),
        ("ENCRYPTION_KEY", s.ENCRYPTION_KEY),
        ("SUPABASE_URL", s.SUPABASE_URL),
        ("SUPABASE_KEY or SUPABASE_ANON_KEY", s.supabase_anon_key),
        ("SUPABASE_SERVICE_ROLE_KEY", s.SUPABASE_SERVICE_ROLE_KEY),
        ("DATABASE_URL", s.DATABASE_URL),
        ("REDIS_URL", s.REDIS_URL),
        ("CLOUDFLARE_ACCOUNT_ID", s.CLOUDFLARE_ACCOUNT_ID),
        ("CLOUDFLARE_R2_BUCKET", s.CLOUDFLARE_R2_BUCKET),
        ("CLOUDFLARE_R2_ACCESS_KEY", s.CLOUDFLARE_R2_ACCESS_KEY),
        ("CLOUDFLARE_R2_SECRET_KEY", s.CLOUDFLARE_R2_SECRET_KEY),
        ("CLOUDFLARE_R2_PUBLIC_URL", s.CLOUDFLARE_R2_PUBLIC_URL),
        ("CLOUDFLARE_R2_ENDPOINT", s.CLOUDFLARE_R2_ENDPOINT),
        ("RESEND_API_KEY", s.RESEND_API_KEY),
        ("EMAIL_FROM", s.EMAIL_FROM),
        ("EMAIL_REPLY_TO", s.EMAIL_REPLY_TO),
        ("RAZORPAY_KEY_ID", s.RAZORPAY_KEY_ID),
        ("RAZORPAY_KEY_SECRET", s.RAZORPAY_KEY_SECRET),
        ("RAZORPAY_WEBHOOK_SECRET", s.RAZORPAY_WEBHOOK_SECRET),
        ("FRONTEND_URL", s.FRONTEND_URL),
        ("ADMIN_URL", s.ADMIN_URL),
    ]

    missing = [name for name, value in required if not value]

    if missing:
        lines = "\n  ".join(missing)
        raise SystemExit(
            f"\n[Hadha.co] Application refused to start. "
            f"The following required environment variables are missing or empty:\n\n  {lines}\n\n"
            f"Copy .env.example to .env and fill in the missing values.\n"
        )

    # Validate Resend API key format — all Resend keys begin with "re_".
    # A wrong-format key always produces a 401 at send time; better to catch
    # it at startup before any requests arrive.
    if s.RESEND_API_KEY and not s.RESEND_API_KEY.startswith("re_"):
        raise SystemExit(
            "\n[Hadha.co] RESEND_API_KEY does not look like a valid Resend API key "
            "(expected it to start with 're_').\n"
            "Generate a fresh key at https://resend.com/api-keys and update your .env.\n"
        )

    # Validate EMAIL_FROM contains an '@' — catches obvious misconfiguration.
    if s.EMAIL_FROM and "@" not in s.EMAIL_FROM:
        raise SystemExit(
            f"\n[Hadha.co] EMAIL_FROM='{s.EMAIL_FROM}' does not look like a valid email address.\n"
            f"Set it to an address whose domain is verified in your Resend dashboard.\n"
        )

    if s.WHATSAPP_ENABLED:
        wa_required = [
            ("WHATSAPP_PHONE_NUMBER_ID", s.WHATSAPP_PHONE_NUMBER_ID),
            ("WHATSAPP_BUSINESS_ACCOUNT_ID", s.WHATSAPP_BUSINESS_ACCOUNT_ID),
            ("WHATSAPP_ACCESS_TOKEN", s.WHATSAPP_ACCESS_TOKEN),
        ]
        wa_missing = [name for name, value in wa_required if not value]
        if wa_missing:
            lines = "\n  ".join(wa_missing)
            raise SystemExit(
                f"\n[Hadha.co] WHATSAPP_ENABLED=true but the following credentials are missing:\n\n"
                f"  {lines}\n\n"
                f"Either set the missing variables or set WHATSAPP_ENABLED=false.\n"
            )


def validate_production_safety(s: Settings) -> None:
    """
    Called at startup AFTER validate_required_settings.
    Blocks the server from starting in production with known-insecure
    configurations.  Called only when APP_ENV == "production".
    """
    violations: list[str] = []

    # Dev auth must be disabled in production.
    if s.ENABLE_DEV_AUTH:
        violations.append(
            "ENABLE_DEV_AUTH=true in production — dev login endpoint would be accessible. "
            "Set ENABLE_DEV_AUTH=false."
        )

    # Debug mode must be off in production.
    if s.APP_DEBUG:
        violations.append(
            "APP_DEBUG=true in production — exposes stack traces and debug info. "
            "Set APP_DEBUG=false."
        )

    # SQL logging must be off in production.
    if s.LOG_SQL:
        violations.append(
            "LOG_SQL=true in production — logs full SQL including parameter values. "
            "Set LOG_SQL=false."
        )

    # Wildcard origin is insecure.
    if "*" in s.allowed_origins_list:
        violations.append(
            "ALLOWED_ORIGINS contains '*' — any site can make cross-origin requests. "
            "Set ALLOWED_ORIGINS to your actual domain(s)."
        )

    # Wildcard host is insecure.
    if "*" in s.allowed_hosts_list:
        violations.append(
            "ALLOWED_HOSTS contains '*' — accepts any Host header. "
            "Set ALLOWED_HOSTS to your actual domain(s)."
        )

    # JWT issuer / JWKS URL must resolve — a misconfigured Supabase URL means
    # every JWT verification silently fails or hits the wrong server.
    if not s.SUPABASE_URL.startswith("https://"):
        violations.append(
            f"SUPABASE_URL='{s.SUPABASE_URL}' does not start with 'https://'. "
            "JWT verification requires a valid Supabase project URL."
        )

    # Secret keys must not use obvious placeholder/default values.
    _placeholder_secrets = {
        "your-secret-key-here",
        "change-me",
        "changeme",
        "super-secret-key",
        "secret",
        "password",
        "test",
        "dummy",
    }
    for field_name in ("SECRET_KEY", "ENCRYPTION_KEY"):
        val = getattr(s, field_name, "")
        if val.lower() in _placeholder_secrets:
            violations.append(
                f"{field_name} appears to be a placeholder/default value. "
                f'Generate a real secret with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )

    # Razorpay test key in production is a warning, not a blocker — payments
    # will simply fail against Razorpay's test environment until the live key
    # is set, but the rest of the app (catalog, CMS, notifications, etc.)
    # must not be taken down for it.
    if s.RAZORPAY_KEY_ID and s.RAZORPAY_KEY_ID.startswith("rzp_test_"):
        print(
            "\n[Hadha.co] WARNING — RAZORPAY_KEY_ID is a test key (rzp_test_*) "
            "in production. Payments will not work against live Razorpay until "
            "RAZORPAY_KEY_ID is set to your live key.\n",
            file=sys.stderr,
        )

    if violations:
        header = (
            "\n[Hadha.co] REFUSING TO START — production safety checks failed.\n\n"
            "The following issues would create a security risk in production:\n"
        )
        body = "\n".join(f"  • {v}" for v in violations)
        raise SystemExit(f"{header}\n{body}\n")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
