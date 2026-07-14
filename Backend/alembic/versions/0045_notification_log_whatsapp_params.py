"""Store WhatsApp retry payload on notification_logs for deterministic retries.

Adds a `whatsapp_params` JSONB column to notification_logs that captures the
minimal WhatsApp template retry payload at send-time: template name, language,
and resolved parameter values. On retry, the dispatcher uses this stored payload
directly instead of re-rendering with an empty context.

Email retries use the already-stored rendered_subject / rendered_body fields —
no additional context is needed.

Revision ID: 0045_notification_log_whatsapp_params
Revises: 0044_notification_registry_refinements
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0045_notification_log_whatsapp_params"
down_revision: str | None = "0044_notification_registry_refinements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_logs",
        sa.Column("whatsapp_params", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_logs", "whatsapp_params")
