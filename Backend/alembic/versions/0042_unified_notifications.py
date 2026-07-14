"""Unified notification platform — additive extensions only.

Builds on the existing notification_templates architecture (channel/subject/
template_body, one row per (event_type, channel) — already correct, see
0030_webhook_email_templates.py and supabase/sql/023_seed_data.sql) rather than
replacing it. Adds: a `variables` JSONB column for Jinja-context/WhatsApp
template-parameter documentation, `rendered_subject`/`rendered_body` on
notification_logs, `whatsapp_enabled` on notification_preferences (sms_enabled
is kept, not dropped — the SMS provider was removed in an earlier change but
the column itself is real/committed and stays per additive-migration policy),
and a new `notification_rules` table that drives the admin Notification Matrix.

No existing column is dropped or renamed. No existing row is deleted. Template
seeding is insert-missing-only (ON CONFLICT (name) DO NOTHING), matching the
pattern already used by 0030_webhook_email_templates.py.

Revision ID: 0042_unified_notifications
Revises: 0041_remove_stale_feature_flags
Create Date: 2026-07-14
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0042_unified_notifications"
down_revision: str | None = "0041_remove_stale_feature_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── New templates (event types not already seeded by 0030 / 023_seed_data.sql) ─
# email: order_cancelled (missing entirely).
# whatsapp: one row per event that defaults to whatsapp_enabled in the event
# registry. `variables.whatsapp_template` is a placeholder — an admin must
# create/approve the actual template in Meta Business Manager and update it
# via the Templates admin UI before these can send.

_NEW_TEMPLATES: list[dict[str, object]] = [
    {
        "name": "order_cancelled_email",
        "channel": "email",
        "event_type": "order_cancelled",
        "subject": "Your order {{order_number}} has been cancelled",
        "body": (
            '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;'
            'font-family:Helvetica,Arial,sans-serif;"><table role="presentation" '
            'width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" '
            'style="padding:24px 12px;"><table role="presentation" width="100%" '
            'style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;">'
            '<tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;">'
            '<span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span>'
            '</td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;color:#1c1b1a;">'
            "Order Cancelled</h2>"
            '<p style="color:#555;line-height:1.6;">Your order <strong>{{order_number}}</strong> '
            "has been cancelled. If you have any questions, please contact our support team.</p>"
            "</td></tr><tr><td "
            'style="padding:16px 32px;background:#f0ede8;color:#999;font-size:12px;'
            'text-align:center;">© Hadha.co · Hallmarked 925 Silver'
            "</td></tr></table></td></tr></table></body></html>"
        ),
        "variables": None,
    },
    {
        "name": "order_created_whatsapp",
        "channel": "whatsapp",
        "event_type": "order_created",
        "subject": None,
        "body": "Order {{order_number}} confirmed. Total: Rs. {{total}}.",
        "variables": {
            "whatsapp_template": "order_created",
            "whatsapp_lang": "en_US",
            "params": ["order_number", "total"],
        },
    },
    {
        "name": "payment_captured_whatsapp",
        "channel": "whatsapp",
        "event_type": "payment_captured",
        "subject": None,
        "body": "Payment of Rs. {{amount}} received for order {{order_number}}.",
        "variables": {
            "whatsapp_template": "payment_captured",
            "whatsapp_lang": "en_US",
            "params": ["order_number", "amount"],
        },
    },
    {
        "name": "payment_failed_whatsapp",
        "channel": "whatsapp",
        "event_type": "payment_failed",
        "subject": None,
        "body": "Payment for order {{order_number}} could not be completed.",
        "variables": {
            "whatsapp_template": "payment_failed",
            "whatsapp_lang": "en_US",
            "params": ["order_number"],
        },
    },
    {
        "name": "order_shipped_whatsapp",
        "channel": "whatsapp",
        "event_type": "order_shipped",
        "subject": None,
        "body": "Order {{order_number}} has shipped. Tracking: {{tracking_number}}.",
        "variables": {
            "whatsapp_template": "order_shipped",
            "whatsapp_lang": "en_US",
            "params": ["order_number", "tracking_number"],
        },
    },
    {
        "name": "order_delivered_whatsapp",
        "channel": "whatsapp",
        "event_type": "order_delivered",
        "subject": None,
        "body": "Order {{order_number}} has been delivered.",
        "variables": {
            "whatsapp_template": "order_delivered",
            "whatsapp_lang": "en_US",
            "params": ["order_number"],
        },
    },
    {
        "name": "order_cancelled_whatsapp",
        "channel": "whatsapp",
        "event_type": "order_cancelled",
        "subject": None,
        "body": "Order {{order_number}} has been cancelled.",
        "variables": {
            "whatsapp_template": "order_cancelled",
            "whatsapp_lang": "en_US",
            "params": ["order_number"],
        },
    },
    {
        "name": "refund_created_whatsapp",
        "channel": "whatsapp",
        "event_type": "refund_created",
        "subject": None,
        "body": "Refund of Rs. {{amount}} initiated for order {{order_number}}.",
        "variables": {
            "whatsapp_template": "refund_created",
            "whatsapp_lang": "en_US",
            "params": ["order_number", "amount"],
        },
    },
    {
        "name": "refund_processed_whatsapp",
        "channel": "whatsapp",
        "event_type": "refund_processed",
        "subject": None,
        "body": "Refund of Rs. {{amount}} processed for order {{order_number}}.",
        "variables": {
            "whatsapp_template": "refund_processed",
            "whatsapp_lang": "en_US",
            "params": ["order_number", "amount"],
        },
    },
    {
        "name": "review_request_whatsapp",
        "channel": "whatsapp",
        "event_type": "review_request",
        "subject": None,
        "body": "How was your order {{order_number}}? Leave a review!",
        "variables": {
            "whatsapp_template": "review_request",
            "whatsapp_lang": "en_US",
            "params": ["order_number"],
        },
    },
]

# ── Notification rules seed (mirrors app/modules/notifications/event_registry.py)

_RULES: list[dict[str, object]] = [
    {
        "event_type": "user_registered",
        "display_name": "Welcome Email",
        "category": "account",
        "description": "Sent when a new customer creates an account.",
        "email_enabled": True,
        "whatsapp_enabled": False,
        "customer_visible": True,
        "display_order": 0,
    },
    {
        "event_type": "order_created",
        "display_name": "Order Confirmation",
        "category": "orders",
        "description": "Sent when a customer places a new order.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 1,
    },
    {
        "event_type": "payment_captured",
        "display_name": "Payment Received",
        "category": "payments",
        "description": "Sent when a payment is successfully captured.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 2,
    },
    {
        "event_type": "payment_failed",
        "display_name": "Payment Failed",
        "category": "payments",
        "description": "Sent when a customer's payment attempt fails.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 3,
    },
    {
        "event_type": "order_shipped",
        "display_name": "Order Shipped",
        "category": "orders",
        "description": "Sent when an order's shipment is dispatched.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 4,
    },
    {
        "event_type": "order_delivered",
        "display_name": "Order Delivered",
        "category": "orders",
        "description": "Sent when an order is marked delivered.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 5,
    },
    {
        "event_type": "order_cancelled",
        "display_name": "Order Cancelled",
        "category": "orders",
        "description": "Sent when an order is cancelled.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 6,
    },
    {
        "event_type": "refund_created",
        "display_name": "Refund Initiated",
        "category": "payments",
        "description": "Sent when a refund is initiated for an order.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 7,
    },
    {
        "event_type": "refund_processed",
        "display_name": "Refund Processed",
        "category": "payments",
        "description": "Sent when a refund has been credited to the customer.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 8,
    },
    {
        "event_type": "refund_failed_admin_alert",
        "display_name": "Refund Failed (Admin Alert)",
        "category": "admin_alerts",
        "description": "Sent to admins when a refund attempt fails and needs manual follow-up.",
        "email_enabled": True,
        "whatsapp_enabled": False,
        "customer_visible": False,
        "display_order": 9,
    },
    {
        "event_type": "review_request",
        "display_name": "Review Request",
        "category": "engagement",
        "description": "Sent after delivery to invite the customer to leave a review.",
        "email_enabled": True,
        "whatsapp_enabled": True,
        "customer_visible": True,
        "display_order": 10,
    },
    {
        "event_type": "low_inventory_alert",
        "display_name": "Low Stock Alert (Admin)",
        "category": "admin_alerts",
        "description": "Sent to admins when a product's stock falls below the low-stock threshold.",
        "email_enabled": True,
        "whatsapp_enabled": False,
        "customer_visible": False,
        "display_order": 11,
    },
]


def upgrade() -> None:
    # 0. Widen existing CHECK constraints to allow the whatsapp channel and
    # the delivered/read lifecycle statuses this feature introduces. These
    # constraints predate WhatsApp support (channel allowed only
    # email/sms/push; status allowed only pending/sent/failed/retrying) —
    # this only adds allowed values, it never removes one.
    op.execute(
        "ALTER TABLE notification_templates DROP CONSTRAINT IF EXISTS notification_templates_channel_check"
    )
    op.execute(
        "ALTER TABLE notification_templates ADD CONSTRAINT notification_templates_channel_check "
        "CHECK (channel = ANY (ARRAY['email'::text, 'sms'::text, 'push'::text, 'whatsapp'::text]))"
    )
    op.execute(
        "ALTER TABLE notification_logs DROP CONSTRAINT IF EXISTS notification_logs_channel_check"
    )
    op.execute(
        "ALTER TABLE notification_logs ADD CONSTRAINT notification_logs_channel_check "
        "CHECK (channel = ANY (ARRAY['email'::text, 'sms'::text, 'push'::text, 'whatsapp'::text]))"
    )
    op.execute(
        "ALTER TABLE notification_logs DROP CONSTRAINT IF EXISTS notification_logs_status_check"
    )
    op.execute(
        "ALTER TABLE notification_logs ADD CONSTRAINT notification_logs_status_check "
        "CHECK (status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text, "
        "'retrying'::text, 'delivered'::text, 'read'::text]))"
    )

    # 1. Additive columns on notification_templates
    op.add_column(
        "notification_templates",
        sa.Column("variables", JSONB, nullable=True),
    )

    # 2. Additive columns on notification_logs.
    # IF NOT EXISTS: an earlier, untracked change already added these two
    # columns directly to the database (outside Alembic) before this
    # migration existed — this keeps upgrade() idempotent against that drift
    # without touching anything else in the table.
    op.execute(
        "ALTER TABLE notification_logs ADD COLUMN IF NOT EXISTS rendered_subject TEXT"
    )
    op.execute(
        "ALTER TABLE notification_logs ADD COLUMN IF NOT EXISTS rendered_body TEXT"
    )

    # 3. Additive column on notification_preferences — sms_enabled is kept.
    op.add_column(
        "notification_preferences",
        sa.Column(
            "whatsapp_enabled", sa.Boolean, server_default="true", nullable=False
        ),
    )

    # 4. New notification_rules table
    op.create_table(
        "notification_rules",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.Text, unique=True, nullable=False),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("category", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, server_default="true", nullable=False),
        sa.Column("email_enabled", sa.Boolean, server_default="true", nullable=False),
        sa.Column(
            "whatsapp_enabled", sa.Boolean, server_default="false", nullable=False
        ),
        sa.Column("priority", sa.Text, server_default="normal", nullable=False),
        sa.Column("retry_policy", JSONB, nullable=True),
        sa.Column("cooldown_seconds", sa.Integer, server_default="0", nullable=False),
        sa.Column(
            "customer_visible", sa.Boolean, server_default="true", nullable=False
        ),
        sa.Column("admin_visible", sa.Boolean, server_default="true", nullable=False),
        sa.Column("is_system", sa.Boolean, server_default="true", nullable=False),
        sa.Column("display_order", sa.Integer, server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 5. Seed missing templates only — never touches existing rows.
    conn = op.get_bind()
    for tpl in _NEW_TEMPLATES:
        conn.execute(
            sa.text(
                "INSERT INTO notification_templates "
                "(name, channel, event_type, subject, template_body, variables, is_active) "
                "VALUES (:name, :channel, :event_type, :subject, :body, "
                "CAST(:variables AS JSONB), TRUE) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {
                **tpl,
                "variables": (
                    None if tpl["variables"] is None else json.dumps(tpl["variables"])
                ),
            },
        )

    # 6. Seed notification rules — never overwrites an existing row.
    for rule in _RULES:
        conn.execute(
            sa.text(
                "INSERT INTO notification_rules "
                "(event_type, display_name, category, description, "
                "email_enabled, whatsapp_enabled, customer_visible, display_order) "
                "VALUES (:event_type, :display_name, :category, :description, "
                ":email_enabled, :whatsapp_enabled, :customer_visible, :display_order) "
                "ON CONFLICT (event_type) DO NOTHING"
            ),
            rule,
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM notification_templates WHERE name IN ("
        + ", ".join(f"'{tpl['name']}'" for tpl in _NEW_TEMPLATES)
        + ")"
    )
    op.drop_table("notification_rules")
    op.drop_column("notification_preferences", "whatsapp_enabled")
    op.drop_column("notification_logs", "rendered_body")
    op.drop_column("notification_logs", "rendered_subject")
    op.drop_column("notification_templates", "variables")

    op.execute(
        "ALTER TABLE notification_logs DROP CONSTRAINT IF EXISTS notification_logs_status_check"
    )
    op.execute(
        "ALTER TABLE notification_logs ADD CONSTRAINT notification_logs_status_check "
        "CHECK (status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text, 'retrying'::text]))"
    )
    op.execute(
        "ALTER TABLE notification_logs DROP CONSTRAINT IF EXISTS notification_logs_channel_check"
    )
    op.execute(
        "ALTER TABLE notification_logs ADD CONSTRAINT notification_logs_channel_check "
        "CHECK (channel = ANY (ARRAY['email'::text, 'sms'::text, 'push'::text]))"
    )
    op.execute(
        "ALTER TABLE notification_templates DROP CONSTRAINT IF EXISTS notification_templates_channel_check"
    )
    op.execute(
        "ALTER TABLE notification_templates ADD CONSTRAINT notification_templates_channel_check "
        "CHECK (channel = ANY (ARRAY['email'::text, 'sms'::text, 'push'::text]))"
    )
