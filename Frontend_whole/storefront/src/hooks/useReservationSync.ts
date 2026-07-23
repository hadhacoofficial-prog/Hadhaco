/**
 * useReservationSync — thin orchestrator for reservation state synchronization.
 *
 * Responsibilities (and ONLY these):
 *   1. Call hydrateReservation when data changes.
 *   2. Mount the SyncBus event listener on mount.
 *
 * Does NOT:
 *   - Import or use queryClient
 *   - Call invalidateQueries
 *   - Subscribe to events directly (delegated to listenReservationEvents)
 *   - Derive business logic (delegated to selectors)
 */

import { useEffect, useRef } from "react";
import { useReservationStore } from "@/stores/reservation";
import {
  hydrateReservation,
  type ReservationSyncData,
} from "@/hooks/reservation/hydrateReservation";
import { listenReservationEvents } from "@/hooks/reservation/listenReservationEvents";

/**
 * Sync reservation data from API/checkout into the Zustand store,
 * and subscribe to SyncBus events for real-time updates.
 */
export function useReservationSync(data: ReservationSyncData | null): void {
  // Hydrate store when data changes
  useEffect(() => {
    if (!data) return;
    hydrateReservation(data);
  }, [data]);

  // Mount the SyncBus event listener once
  const listenerRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!listenerRef.current) {
      listenerRef.current = listenReservationEvents();
    }
    return () => {
      listenerRef.current?.();
      listenerRef.current = null;
    };
  }, []);
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
