import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuthContext } from "@/providers/auth-context";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { ActiveReservationItem, ActiveReservationResponse } from "@/types/shop";

/**
 * Fetches the current user's active (unexpired) reservations.
 * Returns `null` data when the user is not authenticated.
 * Polls every 60 s to keep expiry state fresh.
 */
export function useActiveReservations() {
  const { isAuthenticated, initialized } = useAuthContext();

  const query = useQuery({
    queryKey: queryKeys.orders.activeReservations,
    queryFn: () => api.get<ActiveReservationResponse>("/orders/active-reservations"),
    enabled: initialized && isAuthenticated,
    refetchInterval: 60_000,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  const items = useMemo(() => query.data?.items ?? [], [query.data?.items]);

  /**
   * Get the reservation for a product (optionally a specific variant).
   *
   * The server always reserves against a concrete variant (adding to cart
   * resolves the product's default variant), but a product card or an
   * unpicked cart line has no variantId. With no variant given, fall back to
   * the product's own reservation so the shopper's held item isn't read as
   * "not reserved" (and therefore "Sold Out"). An exact product + variant
   * match always wins, and a given variant never borrows another variant's
   * reservation.
   */
  const getReservation = (
    productId: string,
    variantId?: string | null,
  ): ActiveReservationItem | undefined => {
    const key = reservationKey(productId, variantId ?? null);
    const exact = items.find((item) => reservationKey(item.product_id, item.variant_id) === key);
    if (exact || variantId) return exact;
    return items.find((item) => item.product_id === productId);
  };

  /** Check if a specific product (optionally a variant) is reserved for the current user. */
  const isReserved = (productId: string, variantId?: string | null): boolean =>
    getReservation(productId, variantId) !== undefined;

  /** True if ANY reservation exists for the given product (any variant). */
  const hasAnyReservation = (productId: string): boolean => {
    return items.some((item) => item.product_id === productId);
  };

  /** Time remaining (seconds) until the earliest reservation for a product expires. */
  const secondsUntilExpiry = (productId: string, variantId?: string | null): number => {
    const reservation = getReservation(productId, variantId);
    if (!reservation) return 0;
    const ms = new Date(reservation.expires_at).getTime() - Date.now();
    return Math.max(0, Math.floor(ms / 1000));
  };

  return {
    items,
    isReserved,
    hasAnyReservation,
    getReservation,
    secondsUntilExpiry,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

function reservationKey(productId: string, variantId: string | null): string {
  return `${productId}::${variantId ?? ""}`;
}
