import { create } from "zustand";
import { persist } from "zustand/middleware";
import { getBus, SyncEventType } from "@hadha/shared-api";
import { cartLog } from "@/lib/sync/syncLog";
import { useInventoryStore } from "@/stores/inventory";

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

/** Uniquely identifies a cart line (same product, different variant = different line). */
export const cartLineKey = (productId: string, variantId?: string) =>
  `${productId}::${variantId ?? ""}`;

const lineKey = cartLineKey;

/** Emit CART_CHANGED via SyncBus (dispatches locally AND cross-tab). */
function emitCartChanged(): void {
  try {
    const bus = getBus();
    bus.emit(SyncEventType.CART_CHANGED);
  } catch {
    // SyncBus not initialized yet — graceful degradation
  }
}

/** Notify all listeners after a cart mutation. SyncBus handles cross-tab. */
function notifyCartChange(): void {
  emitCartChanged();
}

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

      add: (productId, qty = 1, snapshot, variantId) => {
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
        });
        cartLog.add(productId, qty, variantId);
        // Optimistic: reflect the add immediately in the live stock store so
        // badges/steppers update across every open page without waiting for
        // a refetch. Must be reversed symmetrically in remove()/setQty()
        // below — an unpaired decrement here previously left products
        // permanently reading a phantom lower stock (or 0/"sold out") for
        // anyone who added then removed an item, since nothing ever
        // incremented it back.
        useInventoryStore.getState().optimisticDecrement(productId, variantId ?? null, qty);
        notifyCartChange();
      },

      remove: (productId, variantId) => {
        const existing = get().lines.find(
          (l) => lineKey(l.productId, l.variantId) === lineKey(productId, variantId),
        );
        set((s) => ({
          lines: s.lines.filter(
            (l) => lineKey(l.productId, l.variantId) !== lineKey(productId, variantId),
          ),
        }));
        cartLog.remove(productId, variantId);
        if (existing) {
          useInventoryStore
            .getState()
            .optimisticIncrement(productId, variantId ?? null, existing.qty);
        }
        notifyCartChange();
      },

      setQty: (productId, qty, variantId) => {
        const existing = get().lines.find(
          (l) => lineKey(l.productId, l.variantId) === lineKey(productId, variantId),
        );
        const prevQty = existing?.qty ?? 0;
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
        }));
        cartLog.setQty(productId, qty, variantId);
        const newQty = Math.max(qty, 0);
        const delta = newQty - prevQty;
        if (delta > 0) {
          useInventoryStore.getState().optimisticDecrement(productId, variantId ?? null, delta);
        } else if (delta < 0) {
          useInventoryStore.getState().optimisticIncrement(productId, variantId ?? null, -delta);
        }
        notifyCartChange();
      },

      clear: () => {
        const count = get().lines.length;
        set({ lines: [] });
        cartLog.clear(count);
        notifyCartChange();
      },
      count: () => get().lines.reduce((n, l) => n + l.qty, 0),
      subtotal: () =>
        get().lines.reduce((n, l) => n + (l.snapshot ? l.snapshot.price * l.qty : 0), 0),
    }),
    { name: "hadha-cart" },
  ),
);
