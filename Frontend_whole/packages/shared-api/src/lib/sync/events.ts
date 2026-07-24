/**
 * Domain Events — the vocabulary of the synchronization system.
 *
 * Every mutation publishes exactly ONE event. Domain modules subscribe
 * to the events they care about and update only their own query keys.
 *
 * Events are lightweight strings with optional typed payloads.
 * The SyncBus routes events to subscribers; cross-tab BroadcastChannel
 * serialises events as JSON.
 */

// ── Domain event types ────────────────────────────────────────────────────────

export const SyncEventType = {
  // Cart
  CART_CHANGED: "CART_CHANGED",

  // Inventory
  INVENTORY_CHANGED: "INVENTORY_CHANGED",

  // Orders
  ORDER_CREATED: "ORDER_CREATED",
  ORDER_CANCELLED: "ORDER_CANCELLED",
  ORDER_STATUS_CHANGED: "ORDER_STATUS_CHANGED",

  // Reservations
  RESERVATION_CREATED: "RESERVATION_CREATED",
  RESERVATION_EXPIRED: "RESERVATION_EXPIRED",

  // Wishlist
  WISHLIST_CHANGED: "WISHLIST_CHANGED",

  // Profile
  PROFILE_UPDATED: "PROFILE_UPDATED",
  ADDRESS_CHANGED: "ADDRESS_CHANGED",

  // Catalog
  PRODUCT_UPDATED: "PRODUCT_UPDATED",
  PRICE_CHANGED: "PRICE_CHANGED",
  COLLECTION_UPDATED: "COLLECTION_UPDATED",

  // CMS
  CMS_PUBLISHED: "CMS_PUBLISHED",

  // Reviews
  REVIEW_SUBMITTED: "REVIEW_SUBMITTED",

  // Auth
  LOGIN: "LOGIN",
  LOGOUT: "LOGOUT",
} as const;

export type SyncEventType = (typeof SyncEventType)[keyof typeof SyncEventType];

// ── Payloads (mapped by event type) ───────────────────────────────────────────

export interface SyncEventPayloads {
  [SyncEventType.CART_CHANGED]: undefined;
  [SyncEventType.INVENTORY_CHANGED]: {
    productIds?: string[];
    /** {productId: availableStock} snapshot taken when the event was
     * published — lets subscribers update their UI directly instead of
     * refetching to learn the same number. */
    availableByProduct?: Record<string, number>;
  };
  [SyncEventType.ORDER_CREATED]: { orderId: string; orderNumber: string };
  [SyncEventType.ORDER_CANCELLED]: { orderId: string };
  [SyncEventType.ORDER_STATUS_CHANGED]: { orderId: string; oldStatus: string; newStatus: string };
  [SyncEventType.RESERVATION_CREATED]: {
    reservationId: string;
    userId?: string;
    productIds?: string[];
    availableByProduct?: Record<string, number>;
  };
  [SyncEventType.RESERVATION_EXPIRED]: {
    reservationId: string;
    userIds?: string[];
    productIds?: string[];
    availableByProduct?: Record<string, number>;
  };
  [SyncEventType.WISHLIST_CHANGED]: undefined;
  [SyncEventType.PROFILE_UPDATED]: undefined;
  [SyncEventType.ADDRESS_CHANGED]: undefined;
  [SyncEventType.PRODUCT_UPDATED]: { productId?: string };
  [SyncEventType.PRICE_CHANGED]: { productId: string };
  [SyncEventType.COLLECTION_UPDATED]: { collectionId?: string };
  [SyncEventType.CMS_PUBLISHED]: undefined;
  [SyncEventType.REVIEW_SUBMITTED]: { productId: string };
  [SyncEventType.LOGIN]: undefined;
  [SyncEventType.LOGOUT]: undefined;
}

// ── Typed event envelope ──────────────────────────────────────────────────────

export interface SyncEvent<T extends SyncEventType = SyncEventType> {
  type: T;
  payload?: SyncEventPayloads[T];
  /** Timestamp (ms) — set by the SyncBus when emitting. */
  ts: number;
  /** Origin tab ID or "server" — used to prevent processing own broadcasts. */
  origin?: string;
  /** Monotonic version counter per origin — used to detect stale/duplicate events. */
  version: number;
  /** Groups related events (e.g., ORDER_CREATED + INVENTORY_CHANGED for same order). */
  correlationId?: string;
  /** Links an optimistic store update to the server confirmation event. */
  mutationId?: string;
}

// ── Listener signature ────────────────────────────────────────────────────────

export type SyncListener<T extends SyncEventType = SyncEventType> = (
  event: SyncEvent<T>,
) => void | Promise<void>;

// ── Serialisation helpers (for BroadcastChannel) ──────────────────────────────

export function serializeEvent(event: SyncEvent): string {
  return JSON.stringify(event);
}

export function deserializeEvent(raw: string): SyncEvent | null {
  try {
    return JSON.parse(raw) as SyncEvent;
  } catch {
    return null;
  }
}
