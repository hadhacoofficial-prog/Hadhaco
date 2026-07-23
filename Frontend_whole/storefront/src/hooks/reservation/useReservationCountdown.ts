import { useEffect, useRef, useState } from "react";

const TICK_INTERVAL_MS = 1_000;
const URGENT_THRESHOLD_S = 60;

export interface CountdownState {
  remainingSeconds: number;
  formatted: string;
  isUrgent: boolean;
  isExpired: boolean;
  progress: number;
}

/**
 * Real-time countdown derived from an ISO 8601 expiry timestamp.
 *
 * This is a pure computation hook — no Zustand store, no duplicate state.
 * Each component that needs a countdown calls this locally with the same
 * `expiresAt` value from `useActiveReservations`.
 *
 * @param expiresAt - ISO 8601 datetime string (server time) or null.
 * @param onExpired - Optional callback fired once when countdown reaches 0.
 */
export function useReservationCountdown(
  expiresAt: string | null,
  onExpired?: () => void,
): CountdownState {
  const calcRemaining = (): number => {
    if (!expiresAt) return 0;
    const ms = new Date(expiresAt).getTime() - Date.now();
    return Math.max(0, Math.floor(ms / 1000));
  };

  const [remaining, setRemaining] = useState(calcRemaining);

  const onExpiredRef = useRef(onExpired);
  onExpiredRef.current = onExpired;
  const firedRef = useRef(false);

  // Recalculate when expiresAt changes (e.g. poll brings fresh data)
  useEffect(() => {
    setRemaining(calcRemaining());
    firedRef.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expiresAt]);

  useEffect(() => {
    if (!expiresAt) return;

    const id = setInterval(() => {
      setRemaining((prev) => {
        const next = Math.max(0, prev - 1);
        if (next <= 0 && !firedRef.current) {
          firedRef.current = true;
          onExpiredRef.current?.();
          clearInterval(id);
        }
        return next;
      });
    }, TICK_INTERVAL_MS);

    return () => clearInterval(id);
  }, [expiresAt]);

  const totalTTL = 10 * 60; // 10 minutes matching backend RESERVATION_TTL_MINUTES
  return {
    remainingSeconds: remaining,
    formatted: formatCountdown(remaining),
    isUrgent: remaining > 0 && remaining <= URGENT_THRESHOLD_S,
    isExpired: remaining <= 0,
    progress: Math.min(100, (remaining / totalTTL) * 100),
  };
}

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/**
 * Shared hook: given a list of reservation items, returns the earliest
 * expiry and a countdown targeting it. Used by checkout to show one
 * unified timer.
 */
export function useEarliestCountdown(
  items: Array<{ expires_at: string }>,
  onExpired?: () => void,
): CountdownState & { earliestExpiry: string | null } {
  const earliest =
    items.length > 0
      ? items.reduce(
          (min, item) => (new Date(item.expires_at) < new Date(min) ? item.expires_at : min),
          items[0].expires_at,
        )
      : null;

  const countdown = useReservationCountdown(earliest, onExpired);

  return { ...countdown, earliestExpiry: earliest };
}
