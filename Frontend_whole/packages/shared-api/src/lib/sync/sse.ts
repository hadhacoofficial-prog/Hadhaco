/**
 * SSE (Server-Sent Events) Module — Cross-User Real-Time Synchronization.
 *
 * Connects to the backend SSE endpoint and feeds received events into the
 * SyncBus so all connected clients update in near-real-time.
 *
 * Flow:
 *   Backend mutation → Redis pub/sub → SSE endpoint → EventSource → SyncBus → UI
 *
 * Falls back to polling if SSE is unavailable or the connection drops.
 */

import { ENV } from "../../config/env";
import { SyncEventType, type SyncEventType as EventType } from "./events";
import type { SyncBus } from "./SyncBus";

// ── Structured logging ───────────────────────────────────────────────────────
const _IS_DEV = typeof window !== "undefined" && (window as any).__DEV__ !== false;
function _log(level: "info" | "warn" | "error", msg: string, ctx?: Record<string, unknown>) {
  const ts = new Date().toISOString().slice(11, 23);
  if (level === "error") console.error(`[SSE] ${ts} ${msg}`, ctx ?? "");
  else if (level === "warn") console.warn(`[SSE] ${ts} ${msg}`, ctx ?? "");
  else if (_IS_DEV) console.log(`[SSE] ${ts} ${msg}`, ctx ?? "");
}

// ── SSE endpoint URL ──────────────────────────────────────────────────────────
// EventSource resolves a relative URL against the current page origin, which
// is wrong for the storefront/admin apps (served from hadha.co /
// admin.hadha.co) since the API lives on a separate origin (api.hadha.co).
// Must build an absolute URL from the same apiBaseUrl the REST client uses.

function _sseEndpoint(): string {
  return `${ENV.apiBaseUrl.replace(/\/+$/, "")}/events/stream`;
}

// ── Reconnection config ───────────────────────────────────────────────────────

const INITIAL_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;
const BACKOFF_MULTIPLIER = 1.5;

// ── Server event type → SyncEvent type mapping ────────────────────────────────

const SERVER_EVENT_MAP: Record<string, EventType> = {
  inventory_changed: SyncEventType.INVENTORY_CHANGED,
  order_created: SyncEventType.ORDER_CREATED,
  order_status_changed: SyncEventType.ORDER_STATUS_CHANGED,
  reservation_created: SyncEventType.RESERVATION_CREATED,
  reservation_expired: SyncEventType.RESERVATION_EXPIRED,
  product_updated: SyncEventType.PRODUCT_UPDATED,
  price_changed: SyncEventType.PRICE_CHANGED,
  collection_updated: SyncEventType.COLLECTION_UPDATED,
  cms_published: SyncEventType.CMS_PUBLISHED,
};

// ── Payload camelization ──────────────────────────────────────────────────────
// Backend sends snake_case (Python dataclass → JSON). Frontend expects camelCase.

function _camelizePayload(payload: unknown): unknown {
  if (!payload || typeof payload !== "object") return payload;
  if (Array.isArray(payload)) return payload.map(_camelizePayload);

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
    const camelKey = key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
    result[camelKey] =
      value && typeof value === "object" && !Array.isArray(value)
        ? _camelizePayload(value)
        : value;
  }
  return result;
}

// ── Connection manager ────────────────────────────────────────────────────────

let _es: EventSource | null = null;
let _retryMs = INITIAL_RETRY_MS;
let _retryTimer: ReturnType<typeof setTimeout> | null = null;
let _bus: SyncBus | null = null;
let _stopped = false;

/**
 * Start listening to the SSE endpoint and forwarding events to the SyncBus.
 * Returns a cleanup function to stop the connection.
 */
export function connectSSE(bus: SyncBus): () => void {
  _bus = bus;
  _stopped = false;
  _connect();

  return () => {
    _stopped = true;
    _disconnect();
  };
}

function _connect(): void {
  if (_stopped || !_bus) return;

  try {
    const endpoint = _sseEndpoint();
    _es = new EventSource(endpoint, { withCredentials: true });

    _es.onopen = () => {
      _retryMs = INITIAL_RETRY_MS;
      _log("info", "Connected to", { endpoint });
    };

    _es.onmessage = (e) => {
      _handleMessage(e.data);
    };

    _es.addEventListener("sync", (e) => {
      _handleMessage((e as MessageEvent).data);
    });

    _es.onerror = () => {
      const readyState = _es?.readyState;
      if (readyState === EventSource.CLOSED) {
        _log("warn", "Connection closed, scheduling reconnect", { retryMs: _retryMs });
        _es?.close();
        _es = null;
        _scheduleReconnect();
      } else if (readyState === EventSource.CONNECTING) {
        _log("info", "Reconnecting...");
      }
    };
  } catch (err) {
    _log("error", "Failed to connect", { error: String(err) });
    _scheduleReconnect();
  }
}

function _disconnect(): void {
  if (_retryTimer) {
    clearTimeout(_retryTimer);
    _retryTimer = null;
  }
  if (_es) {
    _es.close();
    _es = null;
  }
}

function _scheduleReconnect(): void {
  if (_stopped) return;
  _retryTimer = setTimeout(() => {
    _retryMs = Math.min(_retryMs * BACKOFF_MULTIPLIER, MAX_RETRY_MS);
    _connect();
  }, _retryMs);
}

function _handleMessage(data: string): void {
  if (!_bus) return;
  try {
    const parsed = JSON.parse(data) as {
      event?: string;
      type?: string;
      payload?: unknown;
    };

    const eventType = parsed.event ?? parsed.type;
    if (!eventType) return;

    const syncType = SERVER_EVENT_MAP[eventType];
    if (!syncType) return;

    const camelized = _camelizePayload(parsed.payload);
    _log("info", `Received ${syncType}`, { payload: camelized });
    _bus.emitFromServer(syncType, camelized as never);
  } catch {
    // Malformed SSE data — ignore
  }
}
