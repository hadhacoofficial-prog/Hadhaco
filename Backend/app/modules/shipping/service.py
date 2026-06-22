import json
import uuid
from datetime import UTC, datetime

import structlog

from app.core.config import settings
from app.core.events import OrderDeliveredEvent, OrderShippedEvent, event_bus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.shipping.client import DeliveryOneClient
from app.modules.shipping.repository import ShipmentRepository
from app.modules.shipping.schemas import (
    CreateShipmentRequest,
    ShipmentResponse,
    ShippingRateResponse,
    TrackingResponse,
)

log = structlog.get_logger()
_repo = ShipmentRepository()
_client = DeliveryOneClient()

# Pickup address comes from settings (warehouse/store address)
_PICKUP_PINCODE = "400001"  # Override via settings if needed


def _map_do_status(do_status: str) -> str:
    """Map Delivery One status strings to our internal status."""
    mapping = {
        "CREATED": "created",
        "PICKUP_SCHEDULED": "created",
        "PICKED_UP": "picked_up",
        "IN_TRANSIT": "in_transit",
        "OUT_FOR_DELIVERY": "out_for_delivery",
        "DELIVERED": "delivered",
        "CANCELLED": "cancelled",
        "FAILED": "failed",
        "RTO": "failed",  # Return to origin
    }
    return mapping.get(do_status.upper(), "in_transit")


class ShippingService:
    async def create_shipment(
        self,
        db,
        order_id: uuid.UUID,
        payload: CreateShipmentRequest,
    ) -> ShipmentResponse:
        existing = await _repo.get_for_order(db, order_id)
        if existing and existing.status not in ("failed", "cancelled"):
            raise ConflictError("Shipment already exists for this order")

        # Fetch order for address data
        from app.modules.orders.repository import OrderRepository

        order = await OrderRepository().get_by_id(db, order_id)
        if not order:
            raise NotFoundError("Order not found")
        if order.status not in ("confirmed", "processing"):
            raise ValidationError(f"Cannot create shipment for order in '{order.status}' status")

        # Calculate total weight from order items if not provided
        weight = payload.weight_grams
        if not weight:
            # Fetch product weights
            from sqlalchemy import text

            result = await db.execute(
                text(
                    "SELECT COALESCE(SUM(p.weight_grams * oi.quantity), 500) AS total_weight "
                    "FROM order_items oi "
                    "JOIN products p ON p.id = oi.product_id "
                    "WHERE oi.order_id = :order_id"
                ),
                {"order_id": str(order_id)},
            )
            row = result.fetchone()
            weight = int(row[0]) if row and row[0] else 500  # default 500g

        do_payload = {
            "order_reference": order.order_number,
            "weight": weight,
            "length": float(payload.length_cm or 10),
            "width": float(payload.width_cm or 10),
            "height": float(payload.height_cm or 5),
            "cod_amount": 0,  # prepaid
            "pickup_address": {
                "pincode": _PICKUP_PINCODE,
                "name": settings.APP_NAME,
                "phone": "9999999999",  # TODO: move to settings
                "address": "Warehouse Address",
                "city": "Mumbai",
                "state": "Maharashtra",
            },
            "delivery_address": {
                "pincode": order.shipping_postal,
                "name": order.shipping_full_name,
                "phone": order.shipping_phone or "",
                "address": f"{order.shipping_line1} {order.shipping_line2 or ''}".strip(),
                "city": order.shipping_city,
                "state": order.shipping_state,
            },
        }

        try:
            response = await _client.create_shipment(do_payload)
            provider_id = response.get("id") or response.get("shipment_id", "")
            awb = response.get("awb_number") or response.get("tracking_number", "")
            status = "created"
            raw = json.dumps(response)
        except Exception as exc:
            log.error("delivery_one_create_shipment_failed", order_id=str(order_id), error=str(exc))
            # Record failed shipment so admin can retry
            shipment = await _repo.create(
                db,
                {
                    "id": uuid.uuid4(),
                    "order_id": order_id,
                    "status": "failed",
                    "weight_grams": weight,
                    "raw_response": str(exc),
                },
            )
            return ShipmentResponse.model_validate(shipment)

        shipment_data = {
            "id": uuid.uuid4(),
            "order_id": order_id,
            "provider": "delivery_one",
            "provider_shipment_id": provider_id,
            "awb_number": awb,
            "status": status,
            "weight_grams": weight,
            "length_cm": payload.length_cm,
            "width_cm": payload.width_cm,
            "height_cm": payload.height_cm,
            "raw_response": raw,
        }
        shipment = await _repo.create(db, shipment_data)

        # Fetch and store label
        if provider_id:
            try:
                label_bytes = await _client.get_label(provider_id)
                label_url, r2_key = await self._upload_label(label_bytes, order_id, shipment.id)
                await _repo.update(
                    db, shipment.id, {"label_url": label_url, "label_r2_key": r2_key}
                )
                shipment = await _repo.get_by_id(db, shipment.id)
            except Exception as exc:
                log.warning("label_fetch_failed", shipment_id=str(shipment.id), error=str(exc))

        # Update order status to processing
        from app.modules.orders.repository import OrderRepository

        await OrderRepository().update(
            db,
            order_id,
            {
                "status": "processing",
                "tracking_number": awb,
                "shipping_provider": "delivery_one",
            },
        )

        from app.modules.profiles.repository import ProfileRepository

        profile = await ProfileRepository().get_by_id(db, order.user_id)
        await event_bus.publish(
            OrderShippedEvent(
                order_id=str(order_id),
                user_id=str(order.user_id),
                shipment_id=str(shipment.id),
                tracking_number=awb,
                awb=awb,
                tracking_url=f"{settings.FRONTEND_URL.rstrip('/')}/track/{awb}",
                order_number=order.order_number,
                customer_email=(profile.email if profile else "") or "",
            )
        )

        return ShipmentResponse.model_validate(shipment)

    async def get_shipment(
        self, db, order_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> ShipmentResponse:
        # Verify ownership if user_id provided
        if user_id:
            from app.modules.orders.repository import OrderRepository

            order = await OrderRepository().get_by_id(db, order_id)
            if not order or order.user_id != user_id:
                raise NotFoundError("Order not found")

        shipment = await _repo.get_for_order(db, order_id)
        if not shipment:
            raise NotFoundError("Shipment not found")
        return ShipmentResponse.model_validate(shipment)

    async def track(self, db, awb_number: str) -> TrackingResponse:
        """Fetch live tracking from Delivery One and sync events to DB."""
        shipment = await _repo.get_by_awb(db, awb_number)
        if not shipment:
            raise NotFoundError("Shipment not found")

        try:
            data = await _client.track(awb_number)
        except Exception as exc:
            log.warning("tracking_fetch_failed", awb=awb_number, error=str(exc))
            # Return cached events
            return TrackingResponse(
                awb_number=awb_number,
                status=shipment.status,
                estimated_delivery=shipment.estimated_delivery,
                events=list(shipment.events),
            )

        # Sync events
        existing_times = {e.occurred_at for e in shipment.events}
        new_status = shipment.status
        for raw_evt in data.get("events", []):
            try:
                occurred = datetime.fromisoformat(raw_evt["timestamp"])
            except (KeyError, ValueError):
                continue
            if occurred in existing_times:
                continue
            await _repo.add_event(
                db,
                {
                    "id": uuid.uuid4(),
                    "shipment_id": shipment.id,
                    "status": raw_evt.get("status", ""),
                    "description": raw_evt.get("description"),
                    "location": raw_evt.get("location"),
                    "occurred_at": occurred,
                },
            )
            new_status = _map_do_status(raw_evt.get("status", ""))

        update_data: dict = {"status": new_status}
        if new_status == "delivered":
            update_data["delivered_at"] = datetime.now(UTC)
            from app.modules.orders.repository import OrderRepository

            order_repo = OrderRepository()
            order = await order_repo.get_by_id(db, shipment.order_id)
            if order and order.status != "delivered":
                await order_repo.update(
                    db,
                    shipment.order_id,
                    {
                        "status": "delivered",
                        "delivered_at": datetime.now(UTC),
                    },
                )
                from app.modules.profiles.repository import ProfileRepository

                profile = await ProfileRepository().get_by_id(db, order.user_id)
                await event_bus.publish(
                    OrderDeliveredEvent(
                        order_id=str(shipment.order_id),
                        user_id=str(order.user_id),
                        order_number=order.order_number,
                        customer_email=(profile.email if profile else "") or "",
                    )
                )

        await _repo.update(db, shipment.id, update_data)
        shipment = await _repo.get_by_id(db, shipment.id)

        return TrackingResponse(
            awb_number=awb_number,
            status=shipment.status,
            estimated_delivery=shipment.estimated_delivery,
            events=shipment.events,
        )

    async def sync_shipment_status(self, db, order_id: uuid.UUID) -> None:
        """Poll Delivery One for the order's shipment and sync events/status.

        Called by the shipment_sync worker for orders still in transit.
        """
        shipment = await _repo.get_for_order(db, order_id)
        if not shipment or not shipment.awb_number:
            return
        if shipment.status in ("delivered", "cancelled", "failed"):
            return
        await self.track(db, shipment.awb_number)
        await db.commit()

    async def cancel_shipment(self, db, order_id: uuid.UUID, reason: str = "") -> ShipmentResponse:
        shipment = await _repo.get_for_order(db, order_id)
        if not shipment:
            raise NotFoundError("Shipment not found")
        if shipment.status in ("delivered", "cancelled"):
            raise ValidationError(f"Cannot cancel shipment with status '{shipment.status}'")

        if shipment.provider_shipment_id:
            try:
                await _client.cancel_shipment(shipment.provider_shipment_id, reason)
            except Exception as exc:
                log.warning("cancel_shipment_api_failed", error=str(exc))

        updated = await _repo.update(
            db,
            shipment.id,
            {
                "status": "cancelled",
                "cancelled_at": datetime.now(UTC),
                "cancel_reason": reason,
            },
        )
        return ShipmentResponse.model_validate(updated)

    async def get_rates(self, weight_grams: int, pincode_to: str) -> list[ShippingRateResponse]:
        try:
            rates = await _client.get_rates(weight_grams, _PICKUP_PINCODE, pincode_to)
            return [
                ShippingRateResponse(
                    provider="delivery_one",
                    service_name=r.get("service_name", "Standard"),
                    estimated_days=r.get("estimated_days", 5),
                    charge=float(r.get("charge", 99)),
                    is_recommended=r.get("is_recommended", False),
                )
                for r in rates
            ]
        except Exception as exc:
            log.warning("get_rates_failed", error=str(exc))
            # Return default rate on API failure
            return [
                ShippingRateResponse(
                    provider="delivery_one",
                    service_name="Standard Delivery",
                    estimated_days=5,
                    charge=99.0,
                    is_recommended=True,
                )
            ]

    async def _upload_label(
        self, pdf_bytes: bytes, order_id: uuid.UUID, shipment_id: uuid.UUID
    ) -> tuple[str, str]:
        import boto3
        from botocore.config import Config

        r2_key = f"labels/{order_id}/{shipment_id}.pdf"
        client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=r2_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{r2_key}"
        return url, r2_key


# ── Event listener ────────────────────────────────────────────────────────────


async def _on_payment_captured(event) -> None:
    """
    Auto-create shipment when payment is captured for non-COD orders.
    Runs async — failures are logged, not propagated.
    """
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        async with db.begin():
            try:
                svc = ShippingService()
                await svc.create_shipment(
                    db,
                    uuid.UUID(event.order_id),
                    CreateShipmentRequest(order_id=uuid.UUID(event.order_id)),
                )
            except ConflictError:
                pass  # Already exists
            except Exception as exc:
                log.error("auto_create_shipment_failed", order_id=event.order_id, error=str(exc))


def register_shipping_listeners() -> None:
    from app.core.events import PaymentCapturedEvent

    event_bus.on(PaymentCapturedEvent, _on_payment_captured)
