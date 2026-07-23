import { ShieldCheck, Clock, Lock } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useActiveReservations } from "@/hooks/useActiveReservations";
import { useReservationCountdown } from "@/hooks/reservation/useReservationCountdown";

/**
 * Reservation banner shown on the Product Detail Page when the current
 * user has an active reservation for this product/variant.
 *
 * Replaces the normal stock message with a highlighted reservation panel.
 */
export function ReservationBanner({
  productId,
  variantId,
  quantity,
}: {
  productId: string;
  variantId?: string | null;
  quantity?: number;
}) {
  const { getReservation } = useActiveReservations();
  const reservation = getReservation(productId, variantId ?? null);

  const countdown = useReservationCountdown(reservation?.expires_at ?? null);

  if (!reservation || countdown.isExpired) return null;

  return (
    <div
      className={`border rounded-sm p-5 ${countdown.isUrgent ? "border-amber-200 bg-amber-50/50" : "border-blue-200 bg-blue-50/50"}`}
      role="status"
      aria-label="This item is reserved for you"
    >
      <div className="flex items-start gap-4">
        <div
          className={`shrink-0 size-11 flex items-center justify-center rounded-full ${countdown.isUrgent ? "bg-amber-100 text-amber-600" : "bg-blue-100 text-blue-600"}`}
        >
          <ShieldCheck className="size-5" aria-hidden />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3
              className={`font-display text-lg ${countdown.isUrgent ? "text-amber-800" : "text-blue-800"}`}
            >
              Reserved for You
            </h3>
            <Lock
              className={`size-3.5 ${countdown.isUrgent ? "text-amber-500" : "text-blue-500"}`}
              aria-hidden
            />
          </div>
          <p className={`text-sm mt-1 ${countdown.isUrgent ? "text-amber-700" : "text-blue-700"}`}>
            This item is reserved exclusively for you.
            {quantity != null && quantity > 1 && ` (${quantity} units)`}
          </p>

          <div className="mt-3 flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Clock
                className={`size-4 ${countdown.isUrgent ? "text-amber-500" : "text-blue-500"}`}
                aria-hidden
              />
              <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Reservation expires in
              </span>
            </div>
            <span
              className={`font-mono font-bold text-xl tabular-nums ${countdown.isUrgent ? "text-amber-600" : "text-blue-600"}`}
              role="timer"
              aria-label={`Reservation expires in ${countdown.formatted}`}
              aria-live="polite"
            >
              {countdown.formatted}
            </span>
          </div>

          {/* Progress bar */}
          <div className="mt-2 h-1 bg-muted rounded-full overflow-hidden" aria-hidden>
            <div
              className={`h-full transition-all duration-1000 ${countdown.isUrgent ? "bg-amber-500" : "bg-blue-500"}`}
              style={{ width: `${countdown.progress}%` }}
            />
          </div>

          <p className={`mt-3 text-xs ${countdown.isUrgent ? "text-amber-600" : "text-blue-600"}`}>
            Complete checkout before the timer expires to guarantee your item.
          </p>

          <Link
            to="/checkout"
            className={`mt-3 inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] font-medium ${countdown.isUrgent ? "text-amber-700 hover:text-amber-800" : "text-blue-700 hover:text-blue-800"}`}
          >
            Continue to Checkout →
          </Link>
        </div>
      </div>
    </div>
  );
}
