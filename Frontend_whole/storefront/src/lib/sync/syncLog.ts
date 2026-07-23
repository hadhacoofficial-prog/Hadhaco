/**
 * syncLog — Structured observability logger for the synchronization system.
 *
 * All sync-related console output goes through this utility so it can be:
 *   1. Uniformly formatted for dev tools
 *   2. Suppressed in production (via flag)
 *   3. Optionally forwarded to an analytics endpoint
 *
 * In development (import.meta.env.DEV === true), logs are emitted.
 * In production, only errors are emitted.
 */

const IS_DEV = import.meta.env.DEV === true;

type LogLevel = "debug" | "info" | "warn" | "error";

interface LogContext {
  [key: string]: unknown;
}

function _emit(level: LogLevel, tag: string, message: string, ctx?: LogContext): void {
  const prefix = `[${tag}]`;
  const ts = new Date().toISOString().slice(11, 23); // HH:MM:SS.mmm

  if (level === "error") {
    console.error(`${prefix} ${ts} ${message}`, ctx ?? "");
  } else if (level === "warn") {
    console.warn(`${prefix} ${ts} ${message}`, ctx ?? "");
  } else if (IS_DEV) {
    if (level === "debug") {
      console.debug(`${prefix} ${ts} ${message}`, ctx ?? "");
    } else {
      console.log(`${prefix} ${ts} ${message}`, ctx ?? "");
    }
  }
}

// ── Domain-specific loggers ──────────────────────────────────────────────────

/** SyncBus event lifecycle. */
export const syncBusLog = {
  emit(type: string, origin: string, version: number, payload?: unknown) {
    _emit("debug", "SyncBus", `emit ${type}`, { origin, version, payload });
  },
  dispatch(type: string, origin: string, version: number) {
    _emit("debug", "SyncBus", `dispatch ${type}`, { origin, version });
  },
  stale(type: string, origin: string, version: number, lastSeen: number) {
    _emit("debug", "SyncBus", `stale ${type}`, { origin, version, lastSeen });
  },
  broadcast(type: string, version: number) {
    _emit("debug", "SyncBus", `broadcast ${type}`, { version });
  },
};

/** Cart mutations. */
export const cartLog = {
  add(productId: string, qty: number, variantId?: string) {
    _emit("info", "Cart", `add ${qty}x ${productId}`, { variantId });
  },
  remove(productId: string, variantId?: string) {
    _emit("info", "Cart", `remove ${productId}`, { variantId });
  },
  setQty(productId: string, qty: number, variantId?: string) {
    _emit("info", "Cart", `setQty ${productId} → ${qty}`, { variantId });
  },
  clear(lineCount: number) {
    _emit("info", "Cart", `clear ${lineCount} lines`);
  },
};

/** Reservation lifecycle. */
export const reservationLog = {
  created(reservationId: string, productId: string, quantity: number) {
    _emit("info", "Reservation", `created ${reservationId}`, { productId, quantity });
  },
  expired(reservationId: string) {
    _emit("info", "Reservation", `expired ${reservationId}`);
  },
  converted(reservationId: string) {
    _emit("info", "Reservation", `converted ${reservationId}`);
  },
  tick(reservationId: string, remainingSeconds: number) {
    _emit("debug", "Reservation", `tick ${reservationId} → ${remainingSeconds}s`);
  },
};

/** Checkout / payment flow. */
export const checkoutLog = {
  reserveStart() {
    _emit("info", "Checkout", "reserveStart — syncing cart to server");
  },
  reserveSuccess(intentId: string) {
    _emit("info", "Checkout", `reserveSuccess — intent ${intentId}`);
  },
  reserveFail(error: string) {
    _emit("error", "Checkout", `reserveFail — ${error}`);
  },
  paymentOpen(orderId: string) {
    _emit("info", "Checkout", `paymentOpen — order ${orderId}`);
  },
  verifyStart(razorpayPaymentId: string) {
    _emit("info", "Checkout", `verifyStart — ${razorpayPaymentId}`);
  },
  verifySuccess(orderId: string, orderNumber: string) {
    _emit("info", "Checkout", `verifySuccess — order ${orderNumber} (${orderId})`);
  },
  verifyFail(error: string) {
    _emit("error", "Checkout", `verifyFail — ${error}`);
  },
  verifyTimeout() {
    _emit("warn", "Checkout", "verifyTimeout — 30s exceeded");
  },
};

/** Inventory store updates. */
export const inventoryLog = {
  upsert(key: string, source: string, available: number, status: string) {
    _emit("debug", "Inventory", `upsert ${key}`, { source, available, status });
  },
  optimisticDecrement(key: string, qty: number, available: number) {
    _emit("debug", "Inventory", `optimisticDecrement ${key} −${qty}`, { available });
  },
  optimisticIncrement(key: string, qty: number, available: number) {
    _emit("debug", "Inventory", `optimisticIncrement ${key} +${qty}`, { available });
  },
};

/** SSE connection. */
export const sseLog = {
  connected(endpoint: string) {
    _emit("info", "SSE", `connected ${endpoint}`);
  },
  received(type: string, payload?: unknown) {
    _emit("debug", "SSE", `received ${type}`, { payload });
  },
  reconnecting(ms: number) {
    _emit("info", "SSE", `reconnecting in ${ms}ms`);
  },
  error(msg: string) {
    _emit("error", "SSE", msg);
  },
  disconnected() {
    _emit("info", "SSE", "disconnected");
  },
};

/** Buy-Now flow. */
export const buyNowLog = {
  setItems(count: number) {
    _emit("info", "BuyNow", `setItems ${count} items`);
  },
  clear() {
    _emit("info", "BuyNow", "clear");
  },
};
