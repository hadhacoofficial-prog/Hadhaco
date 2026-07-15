"""Add activity-tracking columns to admin_sessions and sweep stale rows.

Adds last_activity_at/last_seen_ip/last_seen_user_agent/device_name/
browser_name/os_name for the admin security dashboard (active sessions list,
login history). Also runs a one-time deploy cleanup of already-expired rows
so environments upgrading from 0047/0048 don't carry stale sessions forward
— the hourly cleanup worker (admin_session_cleanup) takes over from here.

Revision ID: 0049_admin_session_activity_tracking
Revises: 0048_admin_2fa_replay_protection
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET

from alembic import op

revision: str = "0049_admin_session_activity_tracking"
down_revision: str | None = "0048_admin_2fa_replay_protection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_sessions",
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "admin_sessions",
        sa.Column("last_seen_ip", INET, nullable=True),
    )
    op.add_column(
        "admin_sessions",
        sa.Column("last_seen_user_agent", sa.Text, nullable=True),
    )
    op.add_column(
        "admin_sessions",
        sa.Column("device_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "admin_sessions",
        sa.Column("browser_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "admin_sessions",
        sa.Column("os_name", sa.String(100), nullable=True),
    )
    op.create_index(
        "idx_admin_sessions_expires_at",
        "admin_sessions",
        ["expires_at"],
    )

    # One-time deploy cleanup — remove rows already past expiry (or never
    # verified and long stale) so upgrading environments start clean. Never
    # touches an unexpired, currently-verified session.
    op.execute("""
        DELETE FROM admin_sessions
        WHERE (expires_at IS NOT NULL AND expires_at < NOW())
           OR (is_2fa_verified = FALSE AND created_at < NOW() - INTERVAL '24 hours')
        """)


def downgrade() -> None:
    op.drop_index("idx_admin_sessions_expires_at", table_name="admin_sessions")
    op.drop_column("admin_sessions", "os_name")
    op.drop_column("admin_sessions", "browser_name")
    op.drop_column("admin_sessions", "device_name")
    op.drop_column("admin_sessions", "last_seen_user_agent")
    op.drop_column("admin_sessions", "last_seen_ip")
    op.drop_column("admin_sessions", "last_activity_at")
