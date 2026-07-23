/**
 * Centralized Synchronization Engine — Public API
 *
 * Architecture:
 *   1. Initialise once with the app's QueryClient: `initSync(queryClient)`.
 *   2. Every mutation calls exactly ONE emit function (e.g. `afterCartChange()`).
 *   3. Domain modules subscribe to events and invalidate exactly their own queries.
 *   4. Cross-tab sync via BroadcastChannel.
 *   5. Cross-user sync via SSE (server → all connected clients).
 *
 * This replaces scattered `queryClient.invalidateQueries()` calls throughout
 * the codebase, preventing stale UI and missed invalidations.
 */

import type { QueryClient } from "@tanstack/react-query";
import { SyncEventType, type SyncEventPayloads } from "./events";
import { initSyncBus, getSyncBus, type SyncBus } from "./SyncBus";

// Domain modules
import { registerCartSync } from "./cart.sync";
import { registerInventorySync } from "./inventory.sync";
import { registerReservationSync } from "./reservation.sync";
import { registerCheckoutSync } from "./checkout.sync";
import { registerOrderSync } from "./order.sync";
import { registerWishlistSync } from "./wishlist.sync";
import { registerProfileSync } from "./profile.sync";
import { registerHomepageSync } from "./homepage.sync";
import { registerCollectionSync } from "./collection.sync";
import { registerSearchSync } from "./search.sync";
import { registerReviewSync } from "./review.sync";
import { registerAuthSync } from "./auth.sync";

// Re-export event types for consumers
export { SyncEventType } from "./events";
export type { SyncEvent, SyncEventPayloads } from "./events";
export type { SyncBus } from "./SyncBus";

// ── Initialisation ────────────────────────────────────────────────────────────

let _initialised = false;
let _bus: SyncBus | null = null;

/**
 * Initialise the synchronization engine. Must be called once during app startup,
 * after the QueryClient is created. Registers all domain modules and starts
 * cross-tab + cross-user synchronization.
 */
export function initSync(queryClient: QueryClient): void {
  if (_initialised) return;
  _initialised = true;

  _bus = initSyncBus(queryClient);

  // Register all domain modules
  registerCartSync(_bus);
  registerInventorySync(_bus);
  registerReservationSync(_bus);
  registerCheckoutSync(_bus);
  registerOrderSync(_bus);
  registerWishlistSync(_bus);
  registerProfileSync(_bus);
  registerHomepageSync(_bus);
  registerCollectionSync(_bus);
  registerSearchSync(_bus);
  registerReviewSync(_bus);
  registerAuthSync(_bus);

  // Start SSE connection for cross-user sync
  _startSSE(_bus);
}

/**
 * Get the SyncBus instance (after initSync has been called).
 */
export function getBus(): SyncBus {
  if (!_bus) return getSyncBus();
  return _bus;
}

// ── SSE connection (lazy — only starts if browser supports EventSource) ───────

function _startSSE(bus: SyncBus): void {
  if (typeof EventSource === "undefined") return;
  import("./sse").then(({ connectSSE }) => {
    const unsub = connectSSE(bus);
    bus.attachSSE(unsub);
  });
}

// ── Convenience emit functions ─────────────────────────────────────────────────
// Every mutation site calls exactly one of these. They are thin wrappers
// around bus.emit() that provide a clean, discoverable API.

function _emit<T extends SyncEventType>(
  type: T,
  ...payload: SyncEventPayloads[T] extends undefined ? [] : [SyncEventPayloads[T]]
): void {
  if (!_initialised || !_bus) return;
  _bus.emit(type, ...payload);
}

// ── Cart ──────────────────────────────────────────────────────────────────────

/** After a product is added to, removed from, or quantity-changed in the cart. */
export function afterCartChange(): void {
  _emit(SyncEventType.CART_CHANGED);
}

// ── Inventory ─────────────────────────────────────────────────────────────────

/** After inventory stock changes (purchase, admin update, cancellation, refund). */
export function afterInventoryChange(productIds?: string[]): void {
  _emit(SyncEventType.INVENTORY_CHANGED, { productIds });
}

// ── Orders ────────────────────────────────────────────────────────────────────

/** After an order is created (payment verified). */
export function afterOrderCreated(orderId = "", orderNumber = ""): void {
  _emit(SyncEventType.ORDER_CREATED, { orderId, orderNumber });
}

/** After an order is cancelled. */
export function afterOrderCancelled(orderId: string): void {
  _emit(SyncEventType.ORDER_CANCELLED, { orderId });
}

/** After an order status changes. */
export function afterOrderStatusChanged(
  orderId: string,
  oldStatus: string,
  newStatus: string,
): void {
  _emit(SyncEventType.ORDER_STATUS_CHANGED, { orderId, oldStatus, newStatus });
}

// ── Reservations ──────────────────────────────────────────────────────────────

/** After a reservation is created (checkout payment intent). */
export function afterReservationCreated(reservationId = ""): void {
  _emit(SyncEventType.RESERVATION_CREATED, { reservationId });
}

/** After a reservation expires (background worker or checkout timeout). */
export function afterReservationExpired(reservationId = ""): void {
  _emit(SyncEventType.RESERVATION_EXPIRED, { reservationId });
}

// ── Wishlist ──────────────────────────────────────────────────────────────────

/** After wishlist is toggled (add/remove). */
export function afterWishlistChange(): void {
  _emit(SyncEventType.WISHLIST_CHANGED);
}

// ── Profile ───────────────────────────────────────────────────────────────────

/** After profile is updated. */
export function afterProfileUpdate(): void {
  _emit(SyncEventType.PROFILE_UPDATED);
}

/** After an address is created, updated, or deleted. */
export function afterAddressChange(): void {
  _emit(SyncEventType.ADDRESS_CHANGED);
}

// ── Catalog ───────────────────────────────────────────────────────────────────

/** After a product is updated (admin). */
export function afterProductUpdate(productId?: string): void {
  _emit(SyncEventType.PRODUCT_UPDATED, { productId });
}

/** After a product price changes. */
export function afterPriceChanged(productId: string): void {
  _emit(SyncEventType.PRICE_CHANGED, { productId });
}

/** After a collection is updated (admin). */
export function afterCollectionUpdate(collectionId?: string): void {
  _emit(SyncEventType.COLLECTION_UPDATED, { collectionId });
}

// ── CMS ───────────────────────────────────────────────────────────────────────

/** After CMS content is published. */
export function afterCmsPublish(): void {
  _emit(SyncEventType.CMS_PUBLISHED);
}

// ── Reviews ───────────────────────────────────────────────────────────────────

/** After a review is submitted. */
export function afterReviewSubmit(productId: string): void {
  _emit(SyncEventType.REVIEW_SUBMITTED, { productId });
}

// ── Auth ──────────────────────────────────────────────────────────────────────

/** After user logs in. */
export function afterLogin(): void {
  _emit(SyncEventType.LOGIN);
}

/** After user logs out. Clears all cached data. */
export function afterLogout(): void {
  _emit(SyncEventType.LOGOUT);
}

// ── Cross-tab event subscription (for Zustand store sync) ─────────────────────

/**
 * Subscribe to cross-tab sync events. Returns an unsubscribe function.
 * Used by components that need to react to events from other tabs
 * (e.g. clearing Zustand stores on logout).
 */
export function onSyncEvent(
  handler: (event: SyncEventType) => void,
): () => void {
  if (!_initialised || !_bus) return () => {};
  return _bus.subscribeAll((event) => {
    handler(event.type);
  });
}

// ── Nuclear option ────────────────────────────────────────────────────────────

/** Invalidate every customer-facing query (use sparingly). */
export function invalidateAll(): void {
  if (!_bus) return;
  _bus.queryClient.invalidateQueries();
}
