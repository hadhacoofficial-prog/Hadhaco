import { Clock, AlertTriangle } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useReservationCountdown } from "@/hooks/reservation/useReservationCountdown";

/**
 * Countdown bar shown during checkout once items are reserved. Derives
 * remaining time from the server's actual `expiresAt` deadline (ISO 8601) —
 * never a client-guessed fixed window, since the server silently extends
 * the hold from the 2-minute cart TTL to a longer checkout grace period
 * once Razorpay opens (see RESERVATION_CHECKOUT_GRACE_MINUTES). A fixed
 * client-side timer would fire a false "expired" state mid-payment while
 * the server is still holding the stock. `onExpired` fires once when the
 * real deadline passes.
 */
export function ReservationCountdown({
  expiresAt,
  onExpired,
}: {
  expiresAt: string;
  onExpired: () => void;
}) {
  const { remainingSeconds, formatted, isUrgent, isExpired } = useReservationCountdown(
    expiresAt,
    onExpired,
  );
  // progress is cosmetic only — scaled against a nominal 10-minute grace
  // window so the bar doesn't look empty right after the checkout-grace
  // extension kicks in; isExpired/remainingSeconds above are what actually
  // gate behaviour and are always derived from the real expiresAt.
  const pct = isExpired ? 0 : Math.min(100, (remainingSeconds / (10 * 60)) * 100);

  return (
    <div
      role="timer"
      aria-label={`Reservation expires in ${formatted}`}
      aria-live="polite"
      className={`fixed top-0 left-0 right-0 z-50 ${isUrgent ? "bg-amber-600" : "bg-foreground"} text-background`}
    >
      {/* progress bar */}
      <div
        className={`h-0.5 transition-all duration-1000 ${isUrgent ? "bg-white/50" : "bg-white/30"}`}
        style={{ width: `${pct}%` }}
        aria-hidden
      />
      <div className="flex items-center justify-center gap-3 py-2 px-4 text-sm">
        {isUrgent && <AlertTriangle className="size-4 shrink-0" aria-hidden />}
        <Clock className="size-4 shrink-0" aria-hidden />
        <span className="text-[11px] uppercase tracking-[0.18em]">
          {isUrgent ? "Reservation expiring! " : "Your items are reserved for "}
        </span>
        <span className="font-mono font-bold text-base tabular-nums" aria-atomic="true">
          {formatted}
        </span>
      </div>
    </div>
  );
}

/** Modal shown when the reservation window expires mid-checkout. */
export function ReservationExpiredModal({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="res-expired-title"
    >
      <div className="bg-background border border-border p-8 max-w-md w-full text-center shadow-2xl">
        {/* Illustration */}
        <div className="mx-auto mb-6 size-20 flex items-center justify-center">
          <svg viewBox="0 0 80 80" fill="none" className="size-20" aria-hidden>
            <circle
              cx="40"
              cy="40"
              r="38"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-border"
            />
            <rect
              x="24"
              y="28"
              width="32"
              height="26"
              rx="2"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-foreground"
            />
            <path
              d="M30 28v-4a10 10 0 0120 0v4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              className="text-foreground"
            />
            <circle cx="40" cy="41" r="4" fill="currentColor" className="text-foreground" />
            <path
              d="M40 41v5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              className="text-background"
            />
            <circle
              cx="54"
              cy="54"
              r="10"
              fill="white"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-amber-500"
            />
            <path
              d="M54 49v5.5l3 3"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-amber-600"
            />
          </svg>
        </div>
        <h2 id="res-expired-title" className="font-display text-2xl mb-3">
          Reservation Expired
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed mb-7">
          Your reserved items have been released because the reservation window ended before payment
          was completed.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <Link
            to="/cart"
            onClick={onDismiss}
            className="flex-1 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-accent hover:text-accent-foreground transition"
          >
            Return to Cart
          </Link>
          <Link
            to="/collections"
            onClick={onDismiss}
            className="flex-1 border border-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-foreground hover:text-background transition"
          >
            Continue Shopping
          </Link>
        </div>
      </div>
    </div>
  );
}
