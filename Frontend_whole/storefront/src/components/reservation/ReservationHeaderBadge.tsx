import { Lock } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useActiveReservations } from "@/hooks/useActiveReservations";
import { useReservationCountdown } from "@/hooks/reservation/useReservationCountdown";

/**
 * Header reservation indicator badge.
 * Shows the count of reserved items and the earliest countdown.
 * Clicking navigates to the cart.
 */
export function ReservationHeaderBadge({ className = "flex" }: { className?: string }) {
  const { items } = useActiveReservations();

  // Use the earliest expiry for the header badge
  const earliest =
    items.length > 0
      ? items.reduce(
          (min, item) => (new Date(item.expires_at) < new Date(min) ? item.expires_at : min),
          items[0].expires_at,
        )
      : null;

  const countdown = useReservationCountdown(earliest);

  if (!earliest || countdown.isExpired || items.length === 0) return null;

  const count = items.length;

  return (
    <Link
      to="/cart"
      aria-label={`${count} item${count > 1 ? "s" : ""} reserved — ${countdown.formatted} remaining. Go to cart.`}
      className={`${className} items-center gap-1.5 px-2 py-1 text-[10px] uppercase tracking-[0.16em] font-medium rounded-sm transition ${countdown.isUrgent ? "bg-amber-100 text-amber-700 hover:bg-amber-200" : "bg-blue-100 text-blue-700 hover:bg-blue-200"}`}
    >
      <Lock className="size-3" aria-hidden />
      <span className="hidden md:inline">{count} Reserved</span>
      <span className="font-mono font-bold tabular-nums" aria-hidden>
        {countdown.formatted}
      </span>
    </Link>
  );
}

/**
 * Mini badge for the mobile header — shows just the lock + count.
 */
export function ReservationHeaderBadgeMini() {
  const { items } = useActiveReservations();
  const { items: countdownItems } = useActiveReservations();

  const earliest =
    countdownItems.length > 0
      ? countdownItems.reduce(
          (min, item) => (new Date(item.expires_at) < new Date(min) ? item.expires_at : min),
          countdownItems[0].expires_at,
        )
      : null;

  const countdown = useReservationCountdown(earliest);

  if (!earliest || countdown.isExpired || items.length === 0) return null;

  return (
    <Link
      to="/cart"
      aria-label={`${items.length} items reserved`}
      className={`flex items-center gap-1 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.14em] font-medium rounded-sm ${countdown.isUrgent ? "text-amber-600" : "text-blue-600"}`}
    >
      <Lock className="size-2.5" aria-hidden />
      {countdown.formatted}
    </Link>
  );
}
