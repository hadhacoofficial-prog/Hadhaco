import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import UserRole
from app.core.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, comment="References auth.users(id)"
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    primary_image_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("images.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserRole.CUSTOMER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_profiles_email", "email"),
        Index("idx_profiles_role", "role"),
        Index(
            "idx_profiles_active",
            "is_active",
            postgresql_where="is_active = TRUE",
        ),
    )


class Admin2FA(Base):
    __tablename__ = "admin_2fa"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    totp_secret: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # encrypted via Fernet
    backup_codes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )  # JSON array of bcrypt-hashed codes
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last 30s TOTP time-step that successfully verified. Rejects re-submission
    # of an intercepted/captured code within the same (or an earlier) step —
    # pyotp's valid_window tolerance alone does not prevent replay.
    last_used_counter: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Supabase JWT `session_id` claim — correlates this row to one login
    # session so the 2FA gate in app.core.dependencies can look it up per
    # request. Stable across access-token refreshes within the same session.
    supabase_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_2fa_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_admin_sessions_user_id", "user_id"),
        Index("idx_admin_sessions_ip", "ip_address"),
        Index(
            "idx_admin_sessions_user_supabase_session",
            "user_id",
            "supabase_session_id",
            unique=True,
        ),
    )
