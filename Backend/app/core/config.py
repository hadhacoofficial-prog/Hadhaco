from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"

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
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30

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

    # ── SMS ────────────────────────────────────────────────────────────────────
    SMS_ENABLED: bool = False
    MSG91_API_KEY: str = ""
    MSG91_SENDER_ID: str = ""
    MSG91_TEMPLATE_ID: str = ""
    MSG91_ROUTE: int = 4

    # ── Razorpay ───────────────────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str
    RAZORPAY_CURRENCY: str = "INR"

    # ── Delivery One ──────────────────────────────────────────────────────────
    DELIVERY_ONE_BASE_URL: str
    DELIVERY_ONE_API_KEY: str
    DELIVERY_ONE_WEBHOOK_SECRET: str
    DELIVERY_ONE_PICKUP_PINCODE: str = ""

    # ── Frontend ──────────────────────────────────────────────────────────────
    FRONTEND_URL: str
    ADMIN_URL: str

    # ── Auth callbacks ────────────────────────────────────────────────────────
    SUPABASE_AUTH_REDIRECT_URL: str = "http://localhost:3000/auth/callback"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # ── Rate limits ────────────────────────────────────────────────────────────
    RATE_LIMIT_AUTH: int = 10
    RATE_LIMIT_API: int = 200
    RATE_LIMIT_UPLOAD: int = 20
    RATE_LIMIT_WEBHOOK: int = 500

    # ── Worker intervals ──────────────────────────────────────────────────────
    SHIPMENT_SYNC_INTERVAL: int = 300
    REVIEW_REMINDER_DELAY_HOURS: int = 48
    ABANDONED_CART_THRESHOLD_HOURS: int = 1
    ABANDONED_CART_INTERVAL: int = 3600
    INVENTORY_ALERT_INTERVAL: int = 1800
    NOTIFICATION_RETRY_INTERVAL: int = 30

    # ── Business settings ─────────────────────────────────────────────────────
    FREE_SHIPPING_THRESHOLD: int = 999
    SHIPPING_FLAT_RATE: int = 99
    TAX_RATE_GST: float = 3.0
    SELLER_STATE: str = "Maharashtra"
    SELLER_GSTIN: str = ""
    LOW_STOCK_THRESHOLD: int = 5
    ORDER_NUMBER_PREFIX: str = "HD"
    INVOICE_NUMBER_PREFIX: str = "INV"

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
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
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
        ("DELIVERY_ONE_BASE_URL", s.DELIVERY_ONE_BASE_URL),
        ("DELIVERY_ONE_API_KEY", s.DELIVERY_ONE_API_KEY),
        ("DELIVERY_ONE_WEBHOOK_SECRET", s.DELIVERY_ONE_WEBHOOK_SECRET),
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

    if s.SMS_ENABLED:
        msg91_required = [
            ("MSG91_API_KEY", s.MSG91_API_KEY),
            ("MSG91_SENDER_ID", s.MSG91_SENDER_ID),
            ("MSG91_TEMPLATE_ID", s.MSG91_TEMPLATE_ID),
        ]
        msg91_missing = [name for name, value in msg91_required if not value]
        if msg91_missing:
            lines = "\n  ".join(msg91_missing)
            raise SystemExit(
                f"\n[Hadha.co] SMS_ENABLED=true but the following MSG91 credentials are missing:\n\n"
                f"  {lines}\n\n"
                f"Either set the missing variables or set SMS_ENABLED=false.\n"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
