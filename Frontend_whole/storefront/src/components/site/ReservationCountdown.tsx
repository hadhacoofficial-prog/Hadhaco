import { useEffect, useRef, useState } from "react";
import { Clock, AlertTriangle } from "lucide-react";
import { Link } from "@tanstack/react-router";

const RESERVATION_TTL_SECONDS = 10 * 60; // 10 minutes

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/**
 * Fixed countdown bar shown during checkout once items are reserved.
 * `startedAt` is the timestamp (ms) when the reservation was created.
 * `onExpired` fires when the timer reaches zero.
 */
export function ReservationCountdown({
  startedAt,
  onExpired,
}: {
  startedAt: number;
  onExpired: () => void;
}) {
  const [remaining, setRemaining] = useState(() => {
    const elapsed = Math.floor((Date.now() - startedAt) / 1000);
    return Math.max(0, RESERVATION_TTL_SECONDS - elapsed);
  });

  const onExpiredRef = useRef(onExpired);
  onExpiredRef.current = onExpired;

  useEffect(() => {
    if (remaining === 0) {
      onExpiredRef.current();
      return;
    }
    const id = setInterval(() => {
      setRemaining((prev) => {
        const next = prev - 1;
        if (next <= 0) {
          clearInterval(id);
          onExpiredRef.current();
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [remaining]);

  const isUrgent = remaining <= 60;
  const pct = (remaining / RESERVATION_TTL_SECONDS) * 100;

  return (
    <div
      role="timer"
      aria-label={`Reservation expires in ${formatTime(remaining)}`}
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
          {formatTime(remaining)}
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
          Your reserved items have been released because the 10-minute reservation window ended
          before payment was completed.
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
