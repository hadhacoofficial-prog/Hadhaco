"""Final production audit — CTA wording fixes + three missing order-status
templates.

Two changes bundled in this revision, both content-only (no schema change),
both flowing through the same generic sync as 0051/0052:

1. CTA wording aligned to the single-primary-action spec (Order Placed →
   View Order, Packed → Track Order, Shipped → Track Shipment, Delivered →
   View Order, Refund → View Refund Details). Existing rows are snapshotted
   into `notification_template_versions` before the update.

2. Three new templates for order statuses that were reachable via the admin
   `UpdateOrderStatusRequest.status` pattern (`payment_failed`,
   `payment_expired`, `refunded` are all valid direct values) but had no
   corresponding `notification_rules`/`notification_templates` row — an admin
   manually setting one of these statuses produced a silent no-op (no
   customer notification at all). `order_payment_failed`/
   `order_payment_expired`/`order_refunded` close that gap.

Content comes from `app.modules.notifications.emails.catalog`, the single
source of truth. Idempotent — rows already matching the catalog are skipped.

Revision ID: 0053_final_audit_cta_and_status_templates
Revises: 0052_delivered_review_cta_templates
Create Date: 2026-07-16
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.modules.notifications.emails.catalog import ALL_TEMPLATES

revision: str = "0053_final_audit_cta_and_status_templates"
down_revision: str | None = "0052_delivered_review_cta_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TEMPLATE_NAMES = [
    "order_payment_failed_status_email",
    "order_payment_expired_email",
    "order_refunded_status_email",
]


def upgrade() -> None:
    conn = op.get_bind()

    for tpl in ALL_TEMPLATES:
        variables_json = (
            json.dumps(tpl.variables) if tpl.variables is not None else None
        )
        row = (
            conn.execute(
                sa.text(
                    "SELECT id, subject, template_body, variables, version "
                    "FROM notification_templates WHERE name = :name"
                ),
                {"name": tpl.name},
            )
            .mappings()
            .first()
        )

        if row is None:
            conn.execute(
                sa.text(
                    "INSERT INTO notification_templates "
                    "(name, channel, event_type, subject, template_body, "
                    "variables, is_active, version) "
                    "VALUES (:name, :channel, :event_type, :subject, :body, "
                    "CAST(:variables AS JSONB), TRUE, 1) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {
                    "name": tpl.name,
                    "channel": tpl.channel,
                    "event_type": tpl.event_type,
                    "subject": tpl.subject,
                    "body": tpl.body,
                    "variables": variables_json,
                },
            )
            continue

        unchanged = (
            row["template_body"] == tpl.body
            and row["subject"] == tpl.subject
            and (row["variables"] or None) == (tpl.variables or None)
        )
        if unchanged:
            continue

        conn.execute(
            sa.text(
                "INSERT INTO notification_template_versions "
                "(template_id, version, subject, template_body, variables) "
                "VALUES (:template_id, :version, :subject, :body, "
                "CAST(:variables AS JSONB)) "
                "ON CONFLICT (template_id, version) DO NOTHING"
            ),
            {
                "template_id": row["id"],
                "version": row["version"],
                "subject": row["subject"],
                "body": row["template_body"],
                "variables": (
                    json.dumps(row["variables"])
                    if row["variables"] is not None
                    else None
                ),
            },
        )
        conn.execute(
            sa.text(
                "UPDATE notification_templates "
                "SET subject = :subject, template_body = :body, "
                "variables = CAST(:variables AS JSONB), "
                "version = version + 1, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "subject": tpl.subject,
                "body": tpl.body,
                "variables": variables_json,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text("DELETE FROM notification_templates WHERE name = ANY(:names)"),
        {"names": _NEW_TEMPLATE_NAMES},
    )

    upgraded = [t.name for t in ALL_TEMPLATES if t.name not in _NEW_TEMPLATE_NAMES]
    for name in upgraded:
        row = (
            conn.execute(
                sa.text(
                    "SELECT id, version FROM notification_templates WHERE name = :name"
                ),
                {"name": name},
            )
            .mappings()
            .first()
        )
        if row is None:
            continue
        snap = (
            conn.execute(
                sa.text(
                    "SELECT version, subject, template_body, variables "
                    "FROM notification_template_versions "
                    "WHERE template_id = :tid AND version < :v "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"tid": row["id"], "v": row["version"]},
            )
            .mappings()
            .first()
        )
        if snap is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE notification_templates "
                "SET subject = :subject, template_body = :body, "
                "variables = CAST(:variables AS JSONB), version = :version, "
                "updated_at = NOW() WHERE id = :id"
            ),
            {
                "id": row["id"],
                "subject": snap["subject"],
                "body": snap["template_body"],
                "variables": (
                    json.dumps(snap["variables"])
                    if snap["variables"] is not None
                    else None
                ),
                "version": snap["version"],
            },
        )
