"""Add admin_2fa and admin_sessions tables for two-factor authentication.

Creates the admin_2fa table to store encrypted TOTP secrets and bcrypt-hashed
backup codes for admin accounts that opt into 2FA. Also creates admin_sessions
to track active admin sessions with device/IP metadata.

Revision ID: 0046_admin_2fa_and_sessions
Revises: 0045_notification_log_whatsapp_params
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from alembic import op

revision: str = "0046_admin_2fa_and_sessions"
down_revision: str | None = "0045_notification_log_whatsapp_params"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_2fa",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("totp_secret", sa.Text, nullable=False),
        sa.Column(
            "backup_codes",
            sa.Text,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "enabled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "admin_sessions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ip_address", INET, nullable=False),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("device_hash", sa.String(64), nullable=True),
        sa.Column("location", JSONB, nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_admin_sessions_user_id",
        "admin_sessions",
        ["user_id"],
    )
    op.create_index(
        "idx_admin_sessions_ip",
        "admin_sessions",
        ["ip_address"],
    )


def downgrade() -> None:
    op.drop_index("idx_admin_sessions_ip", table_name="admin_sessions")
    op.drop_index("idx_admin_sessions_user_id", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_table("admin_2fa")
