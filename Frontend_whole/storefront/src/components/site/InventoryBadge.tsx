/** Stock status badge shown on product cards and product detail pages. */
export function InventoryBadge({
  availableStock,
  isReserved = false,
  className = "",
}: {
  availableStock: number;
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

  if (availableStock === 0) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.18em] text-destructive font-medium ${className}`}
        aria-label="Sold out"
      >
        <span className="size-1.5 rounded-full bg-destructive" aria-hidden />
        Sold Out
      </span>
    );
  }

  if (availableStock <= 5) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.18em] text-amber-600 font-medium ${className}`}
        aria-label={`Only ${availableStock} left in stock`}
        aria-live="polite"
      >
        <span className="size-1.5 rounded-full bg-amber-500" aria-hidden />
        Only {availableStock} left
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.18em] text-emerald-600 font-medium ${className}`}
      aria-label="In stock"
    >
      <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
      In Stock
    </span>
  );
}

/** Compact pill badge for product cards (overlaid on image). */
export function StockPill({
  availableStock,
  isReserved = false,
}: {
  availableStock: number;
  isReserved?: boolean;
}) {
  if (isReserved) {
    return (
      <span className="absolute bottom-3 left-3 bg-blue-600/90 text-white text-[10px] tracking-[0.18em] uppercase px-2.5 py-1 pointer-events-none">
        Reserved for You
      </span>
    );
  }
  if (availableStock === 0) {
    return (
      <span className="absolute bottom-3 left-3 bg-destructive/90 text-white text-[10px] tracking-[0.18em] uppercase px-2.5 py-1 pointer-events-none">
        Sold Out
      </span>
    );
  }
  if (availableStock <= 5) {
    return (
      <span className="absolute bottom-3 left-3 bg-amber-600/90 text-white text-[10px] tracking-[0.18em] uppercase px-2.5 py-1 pointer-events-none">
        Only {availableStock} Left
      </span>
    );
  }
  return null;
}
