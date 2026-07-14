"""Canonical registry of business events the notification system reacts to.

This is the single source of truth for `event_type` strings — the Alembic seed
data, the admin Notification Matrix, and `NotificationService`'s listener
registration all read from this list instead of repeating string literals.
Add a new event here first; `sync_notification_rules()` (called at app startup)
then upserts any registry entries missing from `notification_rules` so the DB
never has to be migrated just to add an event type.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import NotificationRule


class NotificationCategory(StrEnum):
    """Standardized categories the admin Notification Matrix groups events by."""

    ORDERS = "orders"
    PAYMENTS = "payments"
    SHIPPING = "shipping"
    CUSTOMER = "customer"
    AUTHENTICATION = "authentication"
    INVENTORY = "inventory"
    CMS = "cms"
    WORKERS = "workers"
    MARKETING = "marketing"
    SUPPORT = "support"
    SYSTEM = "system"


@dataclass(frozen=True)
class NotificationEventDef:
    event_type: str
    display_name: str
    category: NotificationCategory
    description: str
    default_email_enabled: bool
    default_whatsapp_enabled: bool
    customer_visible: bool = True
    admin_visible: bool = True
    is_system: bool = True


NOTIFICATION_EVENTS: list[NotificationEventDef] = [
    NotificationEventDef(
        event_type="user_registered",
        display_name="Welcome Email",
        category=NotificationCategory.AUTHENTICATION,
        description="Sent when a new customer creates an account.",
        default_email_enabled=True,
        default_whatsapp_enabled=False,
    ),
    NotificationEventDef(
        event_type="order_created",
        display_name="Order Confirmation",
        category=NotificationCategory.ORDERS,
        description="Sent when a customer places a new order.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
    NotificationEventDef(
        event_type="payment_captured",
        display_name="Payment Received",
        category=NotificationCategory.PAYMENTS,
        description="Sent when a payment is successfully captured.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
    NotificationEventDef(
        event_type="payment_failed",
        display_name="Payment Failed",
        category=NotificationCategory.PAYMENTS,
        description="Sent when a customer's payment attempt fails.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
    NotificationEventDef(
        event_type="order_shipped",
        display_name="Order Shipped",
        category=NotificationCategory.SHIPPING,
        description="Sent when an order's shipment is dispatched.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
    NotificationEventDef(
        event_type="order_delivered",
        display_name="Order Delivered",
        category=NotificationCategory.SHIPPING,
        description="Sent when an order is marked delivered.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
    NotificationEventDef(
        event_type="order_cancelled",
        display_name="Order Cancelled",
        category=NotificationCategory.ORDERS,
        description="Sent when an order is cancelled.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
    NotificationEventDef(
        event_type="refund_created",
        display_name="Refund Initiated",
        category=NotificationCategory.PAYMENTS,
        description="Sent when a refund is initiated for an order.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
    NotificationEventDef(
        event_type="refund_processed",
        display_name="Refund Processed",
        category=NotificationCategory.PAYMENTS,
        description="Sent when a refund has been credited to the customer.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
    NotificationEventDef(
        event_type="refund_failed_admin_alert",
        display_name="Refund Failed (Admin Alert)",
        category=NotificationCategory.SYSTEM,
        description="Sent to admins when a refund attempt fails and needs manual follow-up.",
        default_email_enabled=True,
        default_whatsapp_enabled=False,
        customer_visible=False,
    ),
    NotificationEventDef(
        event_type="review_request",
        display_name="Review Request",
        category=NotificationCategory.MARKETING,
        description="Sent after delivery to invite the customer to leave a review.",
        default_email_enabled=True,
        default_whatsapp_enabled=True,
    ),
]

_BY_EVENT_TYPE: dict[str, NotificationEventDef] = {
    e.event_type: e for e in NOTIFICATION_EVENTS
}


def get_event_def(event_type: str) -> NotificationEventDef | None:
    return _BY_EVENT_TYPE.get(event_type)


async def sync_notification_rules(db: AsyncSession) -> None:
    """Sync every registry entry into `notification_rules`.

    The registry is the authoritative source for *descriptive* metadata
    (display_name/category/description/is_system/display_order) — those are
    refreshed on every startup so renames in code always propagate. Rows
    missing from the DB are inserted with the registry's defaults. Rows that
    already exist keep their admin-editable fields (enabled, email_enabled,
    whatsapp_enabled, customer_visible, admin_visible, priority, retry_policy,
    cooldown_seconds) untouched — an admin's configuration is never
    overwritten. Deprecated events are never deleted here; removing one is a
    deliberate, explicit migration step.
    """
    for order, event in enumerate(NOTIFICATION_EVENTS):
        stmt = (
            pg_insert(NotificationRule)
            .values(
                event_type=event.event_type,
                display_name=event.display_name,
                category=event.category.value,
                description=event.description,
                enabled=True,
                email_enabled=event.default_email_enabled,
                whatsapp_enabled=event.default_whatsapp_enabled,
                customer_visible=event.customer_visible,
                admin_visible=event.admin_visible,
                is_system=event.is_system,
                display_order=order,
            )
            .on_conflict_do_update(
                index_elements=[NotificationRule.event_type],
                set_={
                    "display_name": event.display_name,
                    "category": event.category.value,
                    "description": event.description,
                    "is_system": event.is_system,
                    "display_order": order,
                },
            )
        )
        await db.execute(stmt)
    await db.commit()
