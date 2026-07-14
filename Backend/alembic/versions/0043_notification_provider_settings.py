"""Add notification_provider_settings table.

Additive-only: stores admin-editable, structured config for notification
providers (Resend email, Meta WhatsApp) inside the existing Settings/CMS
domain — a sibling to feature_flags, not a new configuration system. Secret
values (API keys, access tokens) are Fernet-encrypted at the application layer
(app.core.security.encrypt_value) before being written here.

Revision ID: 0043_notification_provider_settings
Revises: 0042_unified_notifications
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0043_notification_provider_settings"
down_revision: str | None = "0042_unified_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_provider_settings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("value_encrypted", sa.Text, nullable=True),
        sa.Column("value_plain", sa.Text, nullable=True),
        sa.Column("is_secret", sa.Boolean, server_default="false", nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("provider", "key", name="uq_provider_setting"),
    )


def downgrade() -> None:
    op.drop_table("notification_provider_settings")
