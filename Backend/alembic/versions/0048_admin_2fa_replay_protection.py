"""Add last_used_counter to admin_2fa for TOTP replay protection.

Security audit finding: pyotp's valid_window tolerance means an intercepted
TOTP code stays accepted for up to ~90s and nothing stopped it being replayed
verbatim within that window. This column records the last time-step that
successfully verified so a repeat submission of the same (or an older) step
is rejected outright.

Revision ID: 0048_admin_2fa_replay_protection
Revises: 0047_admin_session_2fa_verification
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0048_admin_2fa_replay_protection"
down_revision: str | None = "0047_admin_session_2fa_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_2fa",
        sa.Column("last_used_counter", sa.BigInteger, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_2fa", "last_used_counter")
