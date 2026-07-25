"""Customer-facing inventory status — the single place raw stock numbers are
collapsed into the three business states customers are allowed to see.

Consumes available_stock computed elsewhere (ReservationService's
_compute_available / get_available_stock) — does not recompute it. See the
inventory domain plan §0 (single source of truth) and §9.1.
"""

from __future__ import annotations

from enum import StrEnum


class InventoryStatus(StrEnum):
    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


def compute_available_stock(
    stock_quantity: int, reserved_quantity: int, sold_quantity: int
) -> int:
    """Single source of truth for availability: stock - reserved - sold,
    clamped at zero.

    Unlike compute_inventory_status (which takes available_stock as a
    pre-computed input), this is the one place that does the subtraction.
    Every other consumer — SQL views, LATERAL joins, ORM properties — must
    produce a value identical to this function; each such site should carry
    a comment pointing back here so they can't silently drift apart.
    """
    return max(stock_quantity - reserved_quantity - sold_quantity, 0)


def compute_inventory_status(
    available_stock: int,
    low_stock_threshold: int,
    track_inventory: bool,
    allow_backorder: bool,
) -> tuple[InventoryStatus, bool]:
    """Return (inventory_status, can_purchase) for customer display.

    Mirrors the frontend's existing deriveStockStatus
    (storefront/src/stores/inventory.ts) for parity — backorder-eligible
    stock stays purchasable and presents as IN_STOCK, since the spec only
    allows three customer-visible states.
    """
    if not track_inventory:
        return InventoryStatus.IN_STOCK, True
    if available_stock > low_stock_threshold:
        return InventoryStatus.IN_STOCK, True
    if available_stock > 0:
        return InventoryStatus.LOW_STOCK, True
    if allow_backorder:
        return InventoryStatus.IN_STOCK, True
    return InventoryStatus.OUT_OF_STOCK, False
