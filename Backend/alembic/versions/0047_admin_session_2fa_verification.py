"""Add 2FA session-verification columns to admin_sessions.

Correlates each admin_sessions row to a Supabase login session
(supabase_session_id) and tracks whether that session has completed the
TOTP challenge (is_2fa_verified/verified_at/expires_at). This is what
app.core.dependencies checks on every admin-guarded request instead of
trusting any client-side flag.

Revision ID: 0047_admin_session_2fa_verification
Revises: 0046_admin_2fa_and_sessions
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0047_admin_session_2fa_verification"
down_revision: str | None = "0046_admin_2fa_and_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_sessions",
        sa.Column("supabase_session_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "admin_sessions",
        sa.Column(
            "is_2fa_verified",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    op.add_column(
        "admin_sessions",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "admin_sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_admin_sessions_user_supabase_session",
        "admin_sessions",
        ["user_id", "supabase_session_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_admin_sessions_user_supabase_session", table_name="admin_sessions"
    )
    op.drop_column("admin_sessions", "expires_at")
    op.drop_column("admin_sessions", "verified_at")
    op.drop_column("admin_sessions", "is_2fa_verified")
    op.drop_column("admin_sessions", "supabase_session_id")
