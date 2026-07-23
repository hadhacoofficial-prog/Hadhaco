import { Clock, ShieldCheck, Lock, AlertTriangle } from "lucide-react";

interface CountdownTimerProps {
  formatted: string;
  remainingSeconds: number;
  isUrgent: boolean;
  progress: number;
  size?: "sm" | "md" | "lg";
  variant?: "banner" | "inline" | "badge";
  label?: string;
  className?: string;
}

/**
 * Reusable countdown timer display.
 * Does NOT manage its own timer — receives computed state from useReservationCountdown.
 */
export function CountdownTimer({
  formatted,
  isUrgent,
  progress,
  size = "md",
  variant = "inline",
  label,
  className = "",
}: CountdownTimerProps) {
  if (variant === "badge") {
    return (
      <span
        className={`inline-flex items-center gap-1 text-[10px] tracking-[0.16em] uppercase tabular-nums font-mono font-bold ${isUrgent ? "text-amber-600" : "text-blue-600"} ${className}`}
        role="timer"
        aria-label={label ?? `Expires in ${formatted}`}
      >
        <Clock className="size-3" aria-hidden />
        {formatted}
      </span>
    );
  }

  if (variant === "inline") {
    return (
      <span
        className={`inline-flex items-center gap-1.5 tabular-nums font-mono font-bold ${size === "sm" ? "text-xs" : "text-sm"} ${isUrgent ? "text-amber-600" : "text-foreground"} ${className}`}
        role="timer"
        aria-label={label ?? `Expires in ${formatted}`}
      >
        {isUrgent ? (
          <AlertTriangle className="size-3.5 shrink-0 text-amber-500" aria-hidden />
        ) : (
          <Clock className="size-3.5 shrink-0 text-blue-500" aria-hidden />
        )}
        {formatted}
      </span>
    );
  }

  // variant === "banner"
  return (
    <div
      role="timer"
      aria-label={label ?? `Reservation expires in ${formatted}`}
      aria-live="polite"
      className={`flex items-center gap-3 ${className}`}
    >
      <div
        className={`shrink-0 size-10 flex items-center justify-center rounded-full ${isUrgent ? "bg-amber-50 text-amber-600" : "bg-blue-50 text-blue-600"}`}
      >
        {isUrgent ? (
          <AlertTriangle className="size-5" aria-hidden />
        ) : (
          <ShieldCheck className="size-5" aria-hidden />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span
            className={`font-mono font-bold text-2xl tabular-nums ${isUrgent ? "text-amber-600" : "text-foreground"}`}
            aria-atomic="true"
          >
            {formatted}
          </span>
        </div>
        {/* Progress bar */}
        <div className="mt-1.5 h-1 bg-muted rounded-full overflow-hidden" aria-hidden>
          <div
            className={`h-full transition-all duration-1000 ${isUrgent ? "bg-amber-500" : "bg-blue-500"}`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  );
}

interface ReservationShieldProps {
  className?: string;
}

/**
 * Decorative shield icon used in reservation UI to convey safety/protection.
 */
export function ReservationShield({ className = "" }: ReservationShieldProps) {
  return (
    <div className={`inline-flex items-center justify-center ${className}`} aria-hidden="true">
      <Lock className="size-4" />
    </div>
  );
}
