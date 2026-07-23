import { ShieldCheck, Lock, Clock, AlertTriangle } from "lucide-react";
import { useActiveReservations } from "@/hooks/useActiveReservations";
import { useReservationCountdown } from "@/hooks/reservation/useReservationCountdown";

/**
 * Sticky checkout reservation banner.
 * Shows the overall reservation timer (based on earliest expiry)
 * and provides a "Purchase Protected" indicator.
 */
export function ReservationCheckoutBanner({ className = "" }: { className?: string }) {
  const { items } = useActiveReservations();

  // Use the earliest expiry for the overall timer
  const earliest =
    items.length > 0
      ? items.reduce(
          (min, item) => (new Date(item.expires_at) < new Date(min) ? item.expires_at : min),
          items[0].expires_at,
        )
      : null;

  const countdown = useReservationCountdown(earliest);

  if (!earliest || countdown.isExpired || items.length === 0) return null;

  const totalReservedQty = items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <div
      className={`border-b ${countdown.isUrgent ? "border-amber-200 bg-amber-50" : "border-blue-200 bg-blue-50"}`}
      role="status"
      aria-label={`Your items are reserved — ${countdown.formatted} remaining`}
    >
      <div className="max-w-6xl mx-auto px-4 md:px-8 py-3">
        <div className="flex items-center gap-4">
          <div
            className={`shrink-0 size-10 flex items-center justify-center rounded-full ${countdown.isUrgent ? "bg-amber-100 text-amber-600" : "bg-blue-100 text-blue-600"}`}
          >
            <ShieldCheck className="size-5" aria-hidden />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h2
                className={`text-sm font-medium ${countdown.isUrgent ? "text-amber-800" : "text-blue-800"}`}
              >
                Your items are reserved
              </h2>
              <Lock
                className={`size-3 ${countdown.isUrgent ? "text-amber-500" : "text-blue-500"}`}
                aria-hidden
              />
            </div>
            <p
              className={`text-xs mt-0.5 ${countdown.isUrgent ? "text-amber-600" : "text-blue-600"}`}
            >
              You have{" "}
              <span
                className={`font-mono font-bold tabular-nums ${countdown.isUrgent ? "text-amber-700" : "text-blue-700"}`}
                aria-label={`Time remaining: ${countdown.formatted}`}
              >
                {countdown.formatted}
              </span>{" "}
              to complete payment. Your inventory is protected until the timer expires.
            </p>
          </div>
          <div className="shrink-0 flex items-center gap-2">
            <Clock
              className={`size-4 ${countdown.isUrgent ? "text-amber-500" : "text-blue-500"}`}
              aria-hidden
            />
            <span
              className={`font-mono font-bold text-lg tabular-nums ${countdown.isUrgent ? "text-amber-600" : "text-blue-600"}`}
              role="timer"
              aria-label={`Reservation expires in ${countdown.formatted}`}
              aria-live="polite"
              aria-atomic="true"
            >
              {countdown.formatted}
            </span>
          </div>
        </div>
        {/* Progress bar */}
        <div className="mt-2 h-0.5 bg-muted rounded-full overflow-hidden" aria-hidden>
          <div
            className={`h-full transition-all duration-1000 ${countdown.isUrgent ? "bg-amber-500" : "bg-blue-500"}`}
            style={{ width: `${countdown.progress}%` }}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Compact "Purchase Protected" indicator shown near the checkout button.
 */
export function PurchaseProtectedIndicator({ className = "" }: { className?: string }) {
  const { items } = useActiveReservations();

  const earliest =
    items.length > 0
      ? items.reduce(
          (min, item) => (new Date(item.expires_at) < new Date(min) ? item.expires_at : min),
          items[0].expires_at,
        )
      : null;

  const countdown = useReservationCountdown(earliest);

  if (!earliest || countdown.isExpired || items.length === 0) return null;

  return (
    <div
      className={`flex items-center gap-2 text-xs ${countdown.isUrgent ? "text-amber-600" : "text-blue-600"} ${className}`}
    >
      <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
      <span>
        Purchase Protected — reserved for{" "}
        <span className="font-mono font-bold tabular-nums">{countdown.formatted}</span>
      </span>
    </div>
  );
}

/**
 * Payment failure state: reservation is still active, show retry prompt.
 */
export function ReservationPaymentFailedBanner({
  onRetry,
  className = "",
}: {
  onRetry: () => void;
  className?: string;
}) {
  const { items } = useActiveReservations();

  const earliest =
    items.length > 0
      ? items.reduce(
          (min, item) => (new Date(item.expires_at) < new Date(min) ? item.expires_at : min),
          items[0].expires_at,
        )
      : null;

  const countdown = useReservationCountdown(earliest);

  if (!earliest || countdown.isExpired || items.length === 0) return null;

  return (
    <div
      className={`flex items-start gap-4 p-5 ${countdown.isUrgent ? "bg-amber-50 border border-amber-200" : "bg-blue-50 border border-blue-200"}`}
      role="alert"
    >
      <AlertTriangle
        className={`size-5 shrink-0 mt-0.5 ${countdown.isUrgent ? "text-amber-500" : "text-blue-500"}`}
        aria-hidden
      />
      <div className="flex-1">
        <p className={`font-medium ${countdown.isUrgent ? "text-amber-800" : "text-blue-800"}`}>
          Payment failed — your reservation is still active
        </p>
        <p className={`text-sm mt-1 ${countdown.isUrgent ? "text-amber-600" : "text-blue-600"}`}>
          You have <span className="font-mono font-bold tabular-nums">{countdown.formatted}</span>{" "}
          to complete payment. Retry before the timer expires.
        </p>
      </div>
      <button
        onClick={onRetry}
        className={`shrink-0 text-[11px] uppercase tracking-[0.22em] px-5 py-2.5 transition ${countdown.isUrgent ? "bg-amber-600 text-white hover:bg-amber-700" : "bg-blue-600 text-white hover:bg-blue-700"}`}
      >
        Retry Payment
      </button>
    </div>
  );
}
