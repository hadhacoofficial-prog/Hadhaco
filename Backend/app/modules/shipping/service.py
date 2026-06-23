import uuid
from datetime import UTC, datetime

import structlog

from app.core.config import settings
from app.core.events import OrderDeliveredEvent, OrderShippedEvent, event_bus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.shipping.repository import ShipmentRepository
from app.modules.shipping.schemas import (
    CreateShipmentRequest,
    ShipmentResponse,
    ShippingRateResponse,
    TrackingResponse,
    UpdateShipmentRequest,
)

log = structlog.get_logger()
_repo = ShipmentRepository()


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

        from app.modules.orders.repository import OrderRepository

        order = await OrderRepository().get_by_id(db, order_id)
        if not order:
            raise NotFoundError("Order not found")
        if order.status not in ("confirmed", "processing"):
            raise ValidationError(
                f"Cannot create shipment for order in '{order.status}' status"
            )

        shipment = await _repo.create(
            db,
            {
                "id": uuid.uuid4(),
                "order_id": order_id,
                "provider": payload.courier,
                "awb_number": payload.tracking_number,
                "tracking_url": payload.tracking_url,
                "estimated_delivery": payload.estimated_delivery,
                "status": "created",
            },
        )

        await OrderRepository().update(
            db,
            order_id,
            {
                "status": "shipped",
                "tracking_number": payload.tracking_number,
                "shipping_provider": payload.courier,
            },
        )

        from app.modules.profiles.repository import ProfileRepository

        profile = await ProfileRepository().get_by_id(db, order.user_id)
        await event_bus.publish(
            OrderShippedEvent(
                order_id=str(order_id),
                user_id=str(order.user_id),
                shipment_id=str(shipment.id),
                tracking_number=payload.tracking_number or "",
                awb=payload.tracking_number or "",
                tracking_url=payload.tracking_url or "",
                order_number=order.order_number,
                customer_email=(profile.email if profile else "") or "",
            )
        )

        return ShipmentResponse.model_validate(shipment)

    async def update_shipment(
        self,
        db,
        order_id: uuid.UUID,
        payload: UpdateShipmentRequest,
    ) -> ShipmentResponse:
        shipment = await _repo.get_for_order(db, order_id)
        if not shipment:
            raise NotFoundError("Shipment not found")

        update_data: dict = {}
        if payload.courier is not None:
            update_data["provider"] = payload.courier
        if payload.tracking_number is not None:
            update_data["awb_number"] = payload.tracking_number
        if payload.tracking_url is not None:
            update_data["tracking_url"] = payload.tracking_url
        if payload.estimated_delivery is not None:
            update_data["estimated_delivery"] = payload.estimated_delivery
        if payload.status is not None:
            update_data["status"] = payload.status
            if payload.status == "delivered":
                update_data["delivered_at"] = datetime.now(UTC)

        if update_data:
            updated = await _repo.update(db, shipment.id, update_data)
            assert updated is not None
            shipment = updated

        if payload.status == "delivered":
            from app.modules.orders.repository import OrderRepository

            order_repo = OrderRepository()
            order = await order_repo.get_by_id(db, order_id)
            if order and order.status != "delivered":
                await order_repo.update(
                    db,
                    order_id,
                    {"status": "delivered", "delivered_at": datetime.now(UTC)},
                )
                from app.modules.profiles.repository import ProfileRepository

                profile = await ProfileRepository().get_by_id(db, order.user_id)
                await event_bus.publish(
                    OrderDeliveredEvent(
                        order_id=str(order_id),
                        user_id=str(order.user_id),
                        order_number=order.order_number,
                        customer_email=(profile.email if profile else "") or "",
                    )
                )

        return ShipmentResponse.model_validate(shipment)

    async def get_shipment(
        self, db, order_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> ShipmentResponse:
        if user_id:
            from app.modules.orders.repository import OrderRepository

            order = await OrderRepository().get_by_id(db, order_id)
            if not order or order.user_id != user_id:
                raise NotFoundError("Order not found")

        shipment = await _repo.get_for_order(db, order_id)
        if not shipment:
            raise NotFoundError("Shipment not found")
        return ShipmentResponse.model_validate(shipment)

    async def get_tracking(
        self,
        db,
        order_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> TrackingResponse:
        if user_id:
            from app.modules.orders.repository import OrderRepository

            order = await OrderRepository().get_by_id(db, order_id)
            if not order or order.user_id != user_id:
                raise NotFoundError("Order not found")

        shipment = await _repo.get_for_order(db, order_id)
        if not shipment:
            raise NotFoundError("Shipment not found")
        return TrackingResponse(
            courier=shipment.provider,
            tracking_number=shipment.awb_number,
            tracking_url=shipment.tracking_url,
            status=shipment.status,
            estimated_delivery=shipment.estimated_delivery,
            created_at=shipment.created_at,
        )

    async def cancel_shipment(
        self, db, order_id: uuid.UUID, reason: str = ""
    ) -> ShipmentResponse:
        shipment = await _repo.get_for_order(db, order_id)
        if not shipment:
            raise NotFoundError("Shipment not found")
        if shipment.status in ("delivered", "cancelled"):
            raise ValidationError(
                f"Cannot cancel shipment with status '{shipment.status}'"
            )

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

    async def get_rates(
        self, weight_grams: int, pincode_to: str
    ) -> list[ShippingRateResponse]:
        return [
            ShippingRateResponse(
                provider="standard",
                service_name="Standard Delivery",
                estimated_days=5,
                charge=float(settings.SHIPPING_FLAT_RATE),
                is_recommended=True,
            )
        ]
