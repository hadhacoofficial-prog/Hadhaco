import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CartEntry, CartProductSnapshot } from "./cart";

/**
 * Buy-Now store — completely independent from the cart.
 *
 * Persists to localStorage so the checkout flow survives page refresh
 * and browser interruption (common on mobile during login redirect).
 * Cleared on: payment success, reservation expiry, explicit clear, logout.
 * NEVER modifies or clears the cart store.
 */

export interface BuyNowState {
  items: CartEntry[];
  isActive: boolean;

  setItems: (
    items: { productId: string; qty: number; snapshot?: CartProductSnapshot; variantId?: string }[],
  ) => void;
  clear: () => void;
}

const INITIAL_STATE = { items: [] as CartEntry[], isActive: false };

export const useBuyNowStore = create<BuyNowState>()(
  persist(
    (set) => ({
      ...INITIAL_STATE,

      setItems: (items) =>
        set({
          items: items.map((i) => ({
            productId: i.productId,
            qty: i.qty,
            snapshot: i.snapshot,
            variantId: i.variantId,
          })),
          isActive: true,
        }),

      clear: () => set(INITIAL_STATE),
    }),
    { name: "hadha-buy-now" },
  ),
);
