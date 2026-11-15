import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserCredential(Base):
    """Password + email-verification state for a profile (1:1)."""

    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # NULL for accounts that only ever signed in with Google.
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
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


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_oauth_identity_provider_subject"
        ),
        Index("idx_oauth_identities_user", "user_id"),
    )


class AuthSession(Base):
    """One row per login. ``id`` is the access token's ``session_id`` claim."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SHA-256 hex of the current refresh token; the token itself is never stored.
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Hash of the token just replaced, kept for a short grace window so a
    # parallel refresh from a second tab is not mistaken for token theft.
    prev_refresh_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    surface: Mapped[str] = mapped_column(String(10), nullable=False, default="store")
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("refresh_hash", name="uq_auth_sessions_refresh_hash"),
        Index(
            "idx_auth_sessions_user_active",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "idx_auth_sessions_prev_hash",
            "prev_refresh_hash",
            postgresql_where=text("prev_refresh_hash IS NOT NULL"),
        ),
        Index("idx_auth_sessions_expires", "expires_at"),
    )


class AuthToken(Base):
    """Single-use email-verification / password-reset token (hash only)."""

    __tablename__ = "auth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 of the cookie value held by the browser that requested the link.
    # Lets verification tell "same browser that registered" from "a link that
    # reached someone else's mailbox" (see IdentityService.verify_email).
    binder_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_tokens_token_hash"),
        CheckConstraint(
            "purpose IN ('email_verify', 'password_reset')",
            name="ck_auth_tokens_purpose",
        ),
        Index("idx_auth_tokens_user_purpose", "user_id", "purpose"),
        Index("idx_auth_tokens_expires", "expires_at"),
    )
