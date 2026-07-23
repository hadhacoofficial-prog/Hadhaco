/**
 * Reservation Store — first-class business state for stock reservations.
 *
 * Architecture:
 *   - Zustand owns the reservation state (source of truth)
 *   - React Query fetches from API and hydrates this store
 *   - SyncBus events update this store from other tabs/users
 *   - Mutations update this store optimistically
 *   - Components read from this store, NOT from React Query directly
 *
 * Reservations are time-limited holds on stock during checkout.
 * The countdown timer lives here, not in a React state.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { reservationLog } from "@/lib/sync/syncLog";

// ── Types ─────────────────────────────────────────────────────────────────────

export type ReservationStatus =
  | "none"
  | "pending"
  | "active"
  | "expiring"
  | "expired"
  | "converted"
  | "failed";

export interface ReservationEntry {
  /** Server reservation ID. */
  reservationId: string;

  /** User who owns this reservation. */
  ownerUserId: string;

  /** Product this reservation holds. */
  productId: string;

  /** Variant (if any). */
  variantId: string | null;

  /** Quantity reserved. */
  quantity: number;

  /** Unix timestamp (ms) when reservation was created. */
  createdAt: number;

  /** Unix timestamp (ms) when reservation expires. */
  expiresAt: number;

  /** Remaining seconds on the countdown. */
  remainingSeconds: number;

  /** Derived status. */
  status: ReservationStatus;

  /** Whether this reservation belongs to the current user. */
  isOwn: boolean;
}

// ── Constants ─────────────────────────────────────────────────────────────────

export const RESERVATION_TTL_MS = 10 * 60 * 1000; // 10 minutes
export const RESERVATION_URGENT_THRESHOLD_S = 60; // last 60s = "expiring"

// ── Helpers ───────────────────────────────────────────────────────────────────

function deriveStatus(entry: {
  remainingSeconds: number;
  status: ReservationStatus;
}): ReservationStatus {
  if (entry.status === "converted" || entry.status === "failed") return entry.status;
  if (entry.remainingSeconds <= 0) return "expired";
  if (entry.remainingSeconds <= RESERVATION_URGENT_THRESHOLD_S) return "expiring";
  if (entry.status === "pending") return "pending";
  return "active";
}

// ── Store ─────────────────────────────────────────────────────────────────────

interface ReservationState {
  /** Current reservation (if any). Only one active reservation at a time. */
  reservation: ReservationEntry | null;

  /** Countdown timer interval ID (internal). */
  _timerId: ReturnType<typeof setInterval> | null;

  /** Start the countdown timer. */
  startCountdown: () => void;

  /** Stop the countdown timer. */
  stopCountdown: () => void;

  /** Create a new reservation (from API response or SSE event). */
  createReservation: (data: {
    reservationId: string;
    ownerUserId: string;
    productId: string;
    variantId: string | null;
    quantity: number;
    createdAt?: number;
  }) => void;

  /** Mark reservation as converted (order placed). */
  markConverted: () => void;

  /** Mark reservation as failed (payment failed). */
  markFailed: () => void;

  /** Force-expire reservation (from SSE event). */
  expire: () => void;

  /** Clear reservation (manual dismiss or logout). */
  clear: () => void;

  /** Tick the countdown (called by interval). */
  _tick: () => void;
}

export const useReservationStore = create<ReservationState>()(
  persist(
    (set, get) => ({
      reservation: null,
      _timerId: null,

      startCountdown: () => {
        const { _timerId, reservation } = get();
        if (_timerId) return; // already running
        if (!reservation) return;

        const id = setInterval(() => {
          get()._tick();
        }, 1000);

        set({ _timerId: id });
      },

      stopCountdown: () => {
        const { _timerId } = get();
        if (_timerId) {
          clearInterval(_timerId);
          set({ _timerId: null });
        }
      },

      createReservation: (data) => {
        const now = Date.now();
        const createdAt = data.createdAt ?? now;
        const expiresAt = createdAt + RESERVATION_TTL_MS;
        const remainingSeconds = Math.max(0, Math.floor((expiresAt - now) / 1000));

        const entry: ReservationEntry = {
          reservationId: data.reservationId,
          ownerUserId: data.ownerUserId,
          productId: data.productId,
          variantId: data.variantId,
          quantity: data.quantity,
          createdAt,
          expiresAt,
          remainingSeconds,
          status: deriveStatus({ remainingSeconds, status: "active" }),
          isOwn: true,
        };

        // Stop any existing timer
        get().stopCountdown();

        set({ reservation: entry });

        reservationLog.created(data.reservationId, data.productId, data.quantity);

        // Start countdown
        get().startCountdown();
      },

      markConverted: () => {
        const { reservation, _timerId } = get();
        if (!reservation) return;

        if (_timerId) {
          clearInterval(_timerId);
        }

        reservationLog.converted(reservation.reservationId);

        set({
          reservation: {
            ...reservation,
            status: "converted",
            remainingSeconds: 0,
          },
          _timerId: null,
        });
      },

      markFailed: () => {
        const { reservation, _timerId } = get();
        if (!reservation) return;

        if (_timerId) {
          clearInterval(_timerId);
        }

        set({
          reservation: {
            ...reservation,
            status: "failed",
            remainingSeconds: 0,
          },
          _timerId: null,
        });
      },

      expire: () => {
        const { reservation, _timerId } = get();
        if (!reservation) return;

        if (_timerId) {
          clearInterval(_timerId);
        }

        reservationLog.expired(reservation.reservationId);

        set({
          reservation: {
            ...reservation,
            status: "expired",
            remainingSeconds: 0,
          },
          _timerId: null,
        });
      },

      clear: () => {
        const { _timerId } = get();
        if (_timerId) {
          clearInterval(_timerId);
        }
        set({ reservation: null, _timerId: null });
      },

      _tick: () => {
        const { reservation } = get();
        if (!reservation) return;

        const now = Date.now();
        const remainingSeconds = Math.max(0, Math.floor((reservation.expiresAt - now) / 1000));
        const status = deriveStatus({ remainingSeconds, status: reservation.status });

        if (remainingSeconds <= 0) {
          // Timer expired — stop and update status
          get().stopCountdown();
          set({
            reservation: {
              ...reservation,
              remainingSeconds: 0,
              status: "expired",
            },
          });
          return;
        }

        set({
          reservation: {
            ...reservation,
            remainingSeconds,
            status,
          },
        });
      },
    }),
    {
      name: "hadha-reservation",
      partialize: (state) => ({
        // Only persist the reservation data, not the timer ID
        reservation: state.reservation,
      }),
    },
  ),
);

// ── Memoized Selectors ──────────────────────────────────────────────────────

/** Get the current reservation entry (null if none). */
export function selectReservation() {
  return (state: ReservationState): ReservationEntry | null => state.reservation;
}

/** Get the reservation countdown in MM:SS format. Returns null if no reservation. */
export function selectCountdown() {
  return (state: ReservationState): string | null => {
    const r = state.reservation;
    if (!r) return null;
    const m = Math.floor(r.remainingSeconds / 60);
    const s = r.remainingSeconds % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };
}

/** Get the reservation status. */
export function selectReservationStatus() {
  return (state: ReservationState): ReservationStatus => state.reservation?.status ?? "none";
}

/** Check if reservation is active (not expired, not converted, not failed). */
export function selectReservationActive() {
  return (state: ReservationState): boolean => {
    const r = state.reservation;
    return (
      r !== null && r.status !== "expired" && r.status !== "converted" && r.status !== "failed"
    );
  };
}

/** Check if reservation is expiring (≤60s remaining). */
export function selectReservationExpiring() {
  return (state: ReservationState): boolean => state.reservation?.status === "expiring";
}

/** Check if checkout is possible (has active reservation or no reservation needed). */
export function selectCanCheckout() {
  return (state: ReservationState): boolean => {
    const r = state.reservation;
    // No reservation → can proceed
    if (!r) return true;
    // Active reservation → can proceed
    if (r.status === "active" || r.status === "expiring") return true;
    // Expired/failed reservation → cannot proceed
    return false;
  };
}

/** Get remaining seconds on the countdown. Returns null if no reservation. */
export function selectRemainingSeconds() {
  return (state: ReservationState): number | null => state.reservation?.remainingSeconds ?? null;
}
