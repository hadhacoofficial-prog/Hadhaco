import { create } from "zustand";
import { persist } from "zustand/middleware";
import { getBus, SyncEventType } from "@hadha/shared-api";
import { cartLog } from "@/lib/sync/syncLog";

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

/** Broadcast cart changes to other tabs via BroadcastChannel. */
let _cartChannel: BroadcastChannel | null = null;
function broadcastCartCrossTab(): void {
  try {
    if (!_cartChannel) {
      _cartChannel = new BroadcastChannel("hadha:sync");
    }
    _cartChannel.postMessage("cart-changed");
  } catch {
    // BroadcastChannel unavailable — graceful degradation
  }
}

/** Emit CART_CHANGED via SyncBus for local listeners (inventory sync, etc.). */
function emitCartChanged(): void {
  try {
    const bus = getBus();
    bus.emit(SyncEventType.CART_CHANGED);
  } catch {
    // SyncBus not initialized yet — graceful degradation
  }
}

/** Notify all listeners (SyncBus + cross-tab) after a cart mutation. */
function notifyCartChange(): void {
  emitCartChanged();
  broadcastCartCrossTab();
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
        notifyCartChange();
      },

      remove: (productId, variantId) => {
        set((s) => ({
          lines: s.lines.filter(
            (l) => lineKey(l.productId, l.variantId) !== lineKey(productId, variantId),
          ),
        }));
        cartLog.remove(productId, variantId);
        notifyCartChange();
      },

      setQty: (productId, qty, variantId) => {
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

/**
 * Listen for cross-tab cart changes and re-emit via SyncBus so local
 * listeners (inventory sync, etc.) react to remote tab mutations.
 */
function setupCrossTabListener(): void {
  try {
    if (typeof BroadcastChannel === "undefined") return;
    if (!_cartChannel) {
      _cartChannel = new BroadcastChannel("hadha:sync");
    }
    _cartChannel.onmessage = (event) => {
      if (event.data === "cart-changed") {
        // Another tab changed the cart — re-read from localStorage (persist middleware)
        // and emit SyncBus event so local listeners react
        emitCartChanged();
      }
    };
  } catch {
    // BroadcastChannel unavailable
  }
}

// Set up cross-tab listener on module load
setupCrossTabListener();
