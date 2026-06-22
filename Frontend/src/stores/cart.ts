import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface CartProductSnapshot {
  name: string;
  image: string;
  slug: string;
  sku: string;
  price: number;
  variantName?: string;
}

export interface CartEntry {
  productId: string;
  variantId?: string;
  qty: number;
  snapshot?: CartProductSnapshot;
}

// Internal key that uniquely identifies a cart line (same product, different variants = different lines)
const lineKey = (productId: string, variantId?: string) => `${productId}::${variantId ?? ""}`;

interface CartState {
  lines: CartEntry[];
  isOpen: boolean;
  open: () => void;
  close: () => void;
  add: (
    productId: string,
    qty?: number,
    snapshot?: CartProductSnapshot,
    variantId?: string,
  ) => void;
  remove: (productId: string, variantId?: string) => void;
  setQty: (productId: string, qty: number, variantId?: string) => void;
  clear: () => void;
  count: () => number;
  subtotal: () => number;
}

export const useCart = create<CartState>()(
  persist(
    (set, get) => ({
      lines: [],
      isOpen: false,
      open: () => set({ isOpen: true }),
      close: () => set({ isOpen: false }),

      add: (productId, qty = 1, snapshot, variantId) =>
        set((s) => {
          const key = lineKey(productId, variantId);
          const ex = s.lines.find((l) => lineKey(l.productId, l.variantId) === key);
          const lines = ex
            ? s.lines.map((l) =>
                lineKey(l.productId, l.variantId) === key
                  ? { ...l, qty: l.qty + qty, snapshot: snapshot ?? l.snapshot }
                  : l,
              )
            : [...s.lines, { productId, variantId, qty, snapshot }];
          return { lines, isOpen: true };
        }),

      remove: (productId, variantId) =>
        set((s) => ({
          lines: s.lines.filter(
            (l) => lineKey(l.productId, l.variantId) !== lineKey(productId, variantId),
          ),
        })),

      setQty: (productId, qty, variantId) =>
        set((s) => ({
          lines:
            qty <= 0
              ? s.lines.filter(
                  (l) => lineKey(l.productId, l.variantId) !== lineKey(productId, variantId),
                )
              : s.lines.map((l) =>
                  lineKey(l.productId, l.variantId) === lineKey(productId, variantId)
                    ? { ...l, qty }
                    : l,
                ),
        })),

      clear: () => set({ lines: [] }),
      count: () => get().lines.reduce((n, l) => n + l.qty, 0),
      subtotal: () =>
        get().lines.reduce((n, l) => n + (l.snapshot ? l.snapshot.price * l.qty : 0), 0),
    }),
    { name: "hadha-cart" },
  ),
);
