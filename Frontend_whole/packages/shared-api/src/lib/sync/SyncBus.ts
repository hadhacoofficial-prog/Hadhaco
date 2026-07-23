/**
 * SyncBus — the central nervous system of the synchronization framework.
 *
 * Responsibilities:
 *   1. Route domain events to typed subscribers
 *   2. Broadcast events to other browser tabs via BroadcastChannel
 *   3. Receive cross-tab broadcasts and re-emit locally
 *   4. Optionally forward events to a server-side SSE connection
 *
 * The SyncBus is a singleton — call `initSyncBus(queryClient)` once at startup.
 * Domain modules register themselves via `bus.subscribe(eventType, handler)`.
 * Mutation sites call `bus.emit(eventType, payload)`.
 */

import type { QueryClient } from "@tanstack/react-query";
import {
  SyncEventType,
  type SyncEvent,
  type SyncEventType as SyncEventTypeValue,
  type SyncListener,
  type SyncEventPayloads,
} from "./events";
import { serializeEvent, deserializeEvent } from "./events";

// ── Structured logging ───────────────────────────────────────────────────────
const _IS_DEV = typeof window !== "undefined" && (window as any).__DEV__ !== false;
function _log(msg: string, ctx?: Record<string, unknown>) {
  if (_IS_DEV) {
    const ts = new Date().toISOString().slice(11, 23);
    console.debug(`[SyncBus] ${ts} ${msg}`, ctx ?? "");
  }
}

// ── Singleton ─────────────────────────────────────────────────────────────────

let _bus: SyncBus | null = null;

export function getSyncBus(): SyncBus {
  if (!_bus) throw new Error("SyncBus not initialised — call initSyncBus() first");
  return _bus;
}

export function initSyncBus(queryClient: QueryClient): SyncBus {
  if (_bus) return _bus;
  _bus = new SyncBus(queryClient);
  return _bus;
}

// ── BroadcastChannel name ─────────────────────────────────────────────────────

const CHANNEL_NAME = "hadha:sync";

// ── Tab ID (unique per browser tab — prevents processing own broadcasts) ─────

const TAB_ID = Math.random().toString(36).slice(2, 10);

// ── SyncBus implementation ────────────────────────────────────────────────────

export class SyncBus {
  readonly queryClient: QueryClient;

  /** Typed listener registry: eventType → Set<listener>. */
  private _listeners = new Map<string, Set<SyncListener>>();

  /** BroadcastChannel for cross-tab communication (null if unsupported). */
  private _channel: BroadcastChannel | null = null;

  /** Optional server-sent event source (Phase 7). */
  private _sseUnsub: (() => void) | null = null;

  /** Per-origin monotonic version counter — prevents processing stale events. */
  private _versions = new Map<string, number>();

  constructor(queryClient: QueryClient) {
    this.queryClient = queryClient;

    try {
      this._channel = new BroadcastChannel(CHANNEL_NAME);
      this._channel.onmessage = (e) => {
        const event = deserializeEvent(e.data);
        if (!event || event.origin === TAB_ID) return;
        this._dispatch(event);
      };
    } catch {
      // BroadcastChannel not supported — graceful degradation
    }
  }

  // ── Public API ────────────────────────────────────────────────────────────

  /**
   * Emit a domain event. Dispatches locally + broadcasts to other tabs.
   * This is the ONLY way mutation sites trigger synchronization.
   */
  emit<T extends SyncEventType>(
    type: T,
    ...payload: SyncEventPayloads[T] extends undefined ? [] : [SyncEventPayloads[T]]
  ): void {
    const event: SyncEvent<T> = {
      type,
      payload: payload[0] as SyncEventPayloads[T] | undefined,
      ts: Date.now(),
      origin: TAB_ID,
      version: this._nextVersion(TAB_ID),
    };
    _log(`emit ${type}`, { origin: TAB_ID, version: event.version });
    // Dispatch locally (this tab)
    this._dispatch(event);
    // Broadcast to other tabs
    this._broadcast(event);
  }

  /**
   * Subscribe to a specific event type. Returns an unsubscribe function.
   * Handlers may be async — they run as fire-and-forget (errors are logged, never thrown).
   */
  subscribe<T extends SyncEventTypeValue>(type: T, handler: SyncListener<T>): () => void {
    let set = this._listeners.get(type);
    if (!set) {
      set = new Set();
      this._listeners.set(type, set);
    }
    set.add(handler as SyncListener);
    return () => set!.delete(handler as SyncListener);
  }

  /**
   * Subscribe to ALL events. Returns an unsubscribe function.
   */
  subscribeAll(handler: SyncListener): () => void {
    const types = Object.values(SyncEventType) as string[];
    const unsubs = types.map((t) => this.subscribe(t as SyncEventTypeValue, handler));
    return () => unsubs.forEach((u) => u());
  }

  /**
   * Register an SSE connection that feeds remote events into the bus.
   * Called by the SSE module (Phase 7) when a connection is established.
   */
  attachSSE(unsub: () => void): void {
    this._sseUnsub = unsub;
  }

  /**
   * Emit an event as if it came from the server (SSE).
   * Does NOT broadcast — the server already sent it to all clients.
   */
  emitFromServer<T extends SyncEventType>(
    type: T,
    ...payload: SyncEventPayloads[T] extends undefined ? [] : [SyncEventPayloads[T]]
  ): void {
    const event: SyncEvent<T> = {
      type,
      payload: payload[0] as SyncEventPayloads[T] | undefined,
      ts: Date.now(),
      origin: "server",
      version: this._nextVersion("server"),
    };
    this._dispatch(event);
  }

  /**
   * Cleanup — close BroadcastChannel and SSE.
   */
  destroy(): void {
    this._channel?.close();
    this._channel = null;
    this._sseUnsub?.();
    this._sseUnsub = null;
    this._listeners.clear();
  }

  // ── Internals ─────────────────────────────────────────────────────────────

  /**
   * Get the next monotonic version for an origin.
   * Does NOT store the version — only _isStale() updates the tracked version
   * after a successful dispatch. This prevents locally-emitted events from
   * being marked stale before they reach listeners.
   */
  private _nextVersion(origin: string): number {
    const current = this._versions.get(origin) ?? 0;
    return current + 1;
  }

  /** Check if an event is stale (version ≤ last seen for its origin). */
  private _isStale(event: SyncEvent): boolean {
    if (!event.origin) return false;
    const lastSeen = this._versions.get(event.origin) ?? 0;
    // Allow the event through if its version is > last seen,
    // OR if it's the next expected version (normal flow)
    if (event.version <= lastSeen) {
      _log(`stale ${event.type}`, { origin: event.origin, version: event.version, lastSeen });
      return true;
    }
    // Update the tracked version — only on successful dispatch
    this._versions.set(event.origin, event.version);
    return false;
  }

  /** Dispatch an event to all registered listeners for its type. */
  private _dispatch(event: SyncEvent): void {
    // Skip stale/duplicate events
    if (this._isStale(event)) return;

    const set = this._listeners.get(event.type);
    if (!set) return;
    for (const handler of set) {
      try {
        const result = handler(event);
        if (result instanceof Promise) {
          result.catch((err) => {
            console.error(`[SyncBus] handler error for ${event.type}:`, err);
          });
        }
      } catch (err) {
        console.error(`[SyncBus] handler error for ${event.type}:`, err);
      }
    }
  }

  /** Broadcast an event to other browser tabs. */
  private _broadcast(event: SyncEvent): void {
    try {
      this._channel?.postMessage(serializeEvent(event));
    } catch {
      // Channel closed — graceful degradation
    }
  }
}
