/**
 * hydrateReservation — pure function that writes API data into the Zustand store.
 *
 * Single responsibility: transform reservation API data → store state.
 * No side effects, no subscriptions, no React Query dependency.
 */

import { useReservationStore } from "@/stores/reservation";

export interface ReservationSyncData {
  reservationId: string;
  ownerUserId?: string;
  productId: string;
  variantId: string | null;
  quantity: number;
  createdAt?: number;
}

/**
 * Hydrate the reservation Zustand store from API response data.
 */
export function hydrateReservation(data: ReservationSyncData): void {
  useReservationStore.getState().createReservation({
    reservationId: data.reservationId,
    ownerUserId: data.ownerUserId ?? "current",
    productId: data.productId,
    variantId: data.variantId,
    quantity: data.quantity,
    createdAt: data.createdAt,
  });
}
