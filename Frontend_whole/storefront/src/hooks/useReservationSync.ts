/**
 * useReservationSync — thin orchestrator for reservation state synchronization.
 *
 * Responsibilities (and ONLY this):
 *   1. Call hydrateReservation when data changes.
 *
 * The SyncBus event listener (listenReservationEvents) is mounted once,
 * globally, in router.tsx — not here — so real-time pushes apply on every
 * route.
 *
 * Does NOT:
 *   - Import or use queryClient
 *   - Call invalidateQueries
 *   - Subscribe to events directly (delegated to listenReservationEvents)
 *   - Derive business logic (delegated to selectors)
 */

import { useEffect } from "react";
import { useReservationStore } from "@/stores/reservation";
import {
  hydrateReservation,
  type ReservationSyncData,
} from "@/hooks/reservation/hydrateReservation";

/**
 * Sync reservation data from API/checkout into the Zustand store.
 */
export function useReservationSync(data: ReservationSyncData | null): void {
  useEffect(() => {
    if (!data) return;
    hydrateReservation(data);
  }, [data]);
}

// Re-export selectors and hooks for convenience
export {
  selectReservation,
  selectCountdown,
  selectReservationStatus,
  selectReservationActive,
  selectReservationExpiring,
  selectCanCheckout,
  selectRemainingSeconds,
} from "@/stores/reservation";

/**
 * Read the current reservation from the Zustand store.
 */
export function useReservation() {
  return useReservationStore((s) => s.reservation);
}

/**
 * Check if there's an active (non-expired, non-converted) reservation.
 */
export function useHasActiveReservation() {
  return useReservationStore(selectReservationActiveFn);
}

function selectReservationActiveFn(state: { reservation: { status: string } | null }): boolean {
  const r = state.reservation;
  return r !== null && r.status !== "expired" && r.status !== "converted" && r.status !== "failed";
}
