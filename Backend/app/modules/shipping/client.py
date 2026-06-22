"""
Delivery One API client.
Docs: https://docs.deliveryone.in (placeholder — adapt to actual API schema).
All methods raise httpx.HTTPStatusError on non-2xx; callers must handle.
"""

from typing import Any

import httpx

from app.core.config import settings

_BASE_URL = "https://api.deliveryone.in/v1"  # adjust to real base URL
_TIMEOUT = 15.0


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.DELIVERY_ONE_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


class DeliveryOneClient:
    async def create_shipment(self, payload: dict[str, Any]) -> dict:
        """
        POST /shipments
        Required fields (Delivery One format):
          order_reference, weight, length, width, height,
          pickup_address, delivery_address, cod_amount (0 for prepaid)
        """
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/shipments",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_label(self, shipment_id: str) -> bytes:
        """GET /shipments/{id}/label — returns PDF bytes."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE_URL}/shipments/{shipment_id}/label",
                headers=_headers(),
            )
            resp.raise_for_status()
            return resp.content

    async def track(self, awb_number: str) -> dict:
        """GET /tracking/{awb} — returns tracking events."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE_URL}/tracking/{awb_number}",
                headers=_headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def cancel_shipment(self, shipment_id: str, reason: str = "") -> dict:
        """DELETE /shipments/{id}"""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(
                f"{_BASE_URL}/shipments/{shipment_id}",
                headers=_headers(),
                json={"reason": reason},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_rates(
        self, weight_grams: int, pincode_from: str, pincode_to: str
    ) -> list[dict]:
        """POST /rates — returns available service options with pricing."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/rates",
                headers=_headers(),
                json={
                    "weight": weight_grams,
                    "pickup_pincode": pincode_from,
                    "delivery_pincode": pincode_to,
                },
            )
            resp.raise_for_status()
            return resp.json().get("rates", [])
