import { ShieldCheck, Clock, AlertTriangle } from "lucide-react";
import { useActiveReservations } from "@/hooks/useActiveReservations";
import { useReservationCountdown } from "@/hooks/reservation/useReservationCountdown";

/**
 * Reservation card shown for each reserved item in the cart.
 * Displays per-item countdown and reservation status.
 */
export function ReservationCard({
  productId,
  variantId,
  quantity,
}: {
  productId: string;
  variantId?: string | null;
  quantity: number;
}) {
  const { getReservation } = useActiveReservations();
  const reservation = getReservation(productId, variantId ?? null);

  const countdown = useReservationCountdown(reservation?.expires_at ?? null);

  if (!reservation || countdown.isExpired) return null;

  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-sm border ${countdown.isUrgent ? "border-amber-200 bg-amber-50/50" : "border-blue-200 bg-blue-50/50"}`}
      role="status"
      aria-label={`Reserved for you — ${countdown.formatted} remaining`}
    >
      <div
        className={`shrink-0 size-8 flex items-center justify-center rounded-full ${countdown.isUrgent ? "bg-amber-100 text-amber-600" : "bg-blue-100 text-blue-600"}`}
      >
        <ShieldCheck className="size-4" aria-hidden />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs uppercase tracking-[0.16em] font-medium ${countdown.isUrgent ? "text-amber-700" : "text-blue-700"}`}
          >
            Reserved for You
          </span>
          <Clock
            className={`size-3 ${countdown.isUrgent ? "text-amber-500" : "text-blue-500"}`}
            aria-hidden
          />
        </div>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-xs text-muted-foreground">Qty Reserved: {quantity}</span>
          <span
            className={`font-mono font-bold text-sm tabular-nums ${countdown.isUrgent ? "text-amber-600" : "text-blue-600"}`}
            role="timer"
            aria-label={`Time remaining: ${countdown.formatted}`}
          >
            {countdown.formatted}
          </span>
        </div>
      </div>
      {countdown.isUrgent && (
        <AlertTriangle
          className="size-4 shrink-0 text-amber-500"
          aria-label="Reservation expiring soon"
        />
      )}
    </div>
  );
}

/**
 * Expiry overlay shown when a reservation expires.
 */
export function ReservationExpiredNotice({ className = "" }: { className?: string }) {
  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-sm border border-amber-200 bg-amber-50/50 ${className}`}
      role="alert"
    >
      <AlertTriangle className="size-4 shrink-0 text-amber-500" aria-hidden />
      <div>
        <p className="text-xs font-medium text-amber-800">Reservation Expired</p>
        <p className="text-xs text-amber-600 mt-0.5">
          Your reserved inventory has been released. Please reserve again if stock is still
          available.
        </p>
      </div>
    </div>
  );
}
