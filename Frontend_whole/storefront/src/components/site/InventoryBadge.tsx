import type { CustomerInventoryStatus } from "@/stores/inventory";

/**
 * Stock status badge shown on product cards and product detail pages.
 *
 * Customer inventory presentation rules (inventory domain plan §9): renders
 * ONLY a business state, never a quantity. IN_STOCK renders nothing,
 * LOW_STOCK/OUT_OF_STOCK render a labeled badge. Never pass a raw
 * `availableStock` number into this component — resolve it to a
 * CustomerInventoryStatus first (via the API's `inventory_status` field or
 * `toCustomerStatus` from stores/inventory).
 */
export function InventoryBadge({
  status,
  isReserved = false,
  className = "",
}: {
  status: CustomerInventoryStatus;
  isReserved?: boolean;
  className?: string;
}) {
  if (isReserved) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.18em] text-blue-600 font-medium ${className}`}
        aria-label="Reserved for you"
      >
        <span className="size-1.5 rounded-full bg-blue-500" aria-hidden />
        Reserved for you
      </span>
    );
  }

  if (status === "OUT_OF_STOCK") {
    return (
      <span
        className={`inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.18em] text-destructive font-medium ${className}`}
        aria-label="Out of stock"
      >
        <span className="size-1.5 rounded-full bg-destructive" aria-hidden />
        Out of Stock
      </span>
    );
  }

  if (status === "LOW_STOCK") {
    return (
      <span
        className={`inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.18em] text-amber-600 font-medium ${className}`}
        aria-label="Low stock"
        aria-live="polite"
      >
        <span className="size-1.5 rounded-full bg-amber-500" aria-hidden />
        Low Stock
      </span>
    );
  }

  // IN_STOCK: show nothing.
  return null;
}

/** Compact pill badge for product cards (overlaid on image). */
export function StockPill({
  status,
  isReserved = false,
  countdown,
}: {
  status: CustomerInventoryStatus;
  isReserved?: boolean;
  countdown?: string;
}) {
  if (isReserved) {
    return (
      <span className="absolute bottom-3 left-3 bg-blue-600/90 text-white text-[10px] tracking-[0.18em] uppercase px-2.5 py-1 pointer-events-none flex items-center gap-1.5">
        Reserved for You
        {countdown && <span className="font-mono font-bold tabular-nums">{countdown}</span>}
      </span>
    );
  }
  if (status === "OUT_OF_STOCK") {
    return (
      <span className="absolute bottom-3 left-3 bg-destructive/90 text-white text-[10px] tracking-[0.18em] uppercase px-2.5 py-1 pointer-events-none">
        Sold Out
      </span>
    );
  }
  if (status === "LOW_STOCK") {
    return (
      <span className="absolute bottom-3 left-3 bg-amber-600/90 text-white text-[10px] tracking-[0.18em] uppercase px-2.5 py-1 pointer-events-none">
        Low Stock
      </span>
    );
  }
  return null;
}
