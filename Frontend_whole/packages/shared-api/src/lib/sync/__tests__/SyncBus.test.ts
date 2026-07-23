import { describe, it, expect, beforeEach, vi } from "vitest";
import { SyncBus } from "../SyncBus";
import { SyncEventType, type SyncEvent } from "../events";

// Mock QueryClient
function createMockQueryClient() {
  return {
    invalidateQueries: vi.fn(),
    clear: vi.fn(),
  } as any;
}

describe("SyncBus", () => {
  let bus: SyncBus;
  let qc: ReturnType<typeof createMockQueryClient>;

  beforeEach(() => {
    qc = createMockQueryClient();
    bus = new SyncBus(qc);
  });

  describe("emit and subscribe", () => {
    it("dispatches event to local subscribers", () => {
      const handler = vi.fn();
      bus.subscribe(SyncEventType.CART_CHANGED, handler);

      bus.emit(SyncEventType.CART_CHANGED);

      expect(handler).toHaveBeenCalledTimes(1);
      const event = handler.mock.calls[0][0] as SyncEvent;
      expect(event.type).toBe(SyncEventType.CART_CHANGED);
      expect(event.ts).toBeGreaterThan(0);
      expect(event.version).toBe(1);
    });

    it("does not dispatch to subscribers of other event types", () => {
      const handler = vi.fn();
      bus.subscribe(SyncEventType.ORDER_CREATED, handler);

      bus.emit(SyncEventType.CART_CHANGED);

      expect(handler).not.toHaveBeenCalled();
    });

    it("emits with payload", () => {
      const handler = vi.fn();
      bus.subscribe(SyncEventType.INVENTORY_CHANGED, handler);

      bus.emit(SyncEventType.INVENTORY_CHANGED, { productIds: ["p1", "p2"] });

      const event = handler.mock.calls[0][0] as SyncEvent;
      expect(event.payload).toEqual({ productIds: ["p1", "p2"] });
    });

    it("supports multiple subscribers for same event", () => {
      const handler1 = vi.fn();
      const handler2 = vi.fn();
      bus.subscribe(SyncEventType.CART_CHANGED, handler1);
      bus.subscribe(SyncEventType.CART_CHANGED, handler2);

      bus.emit(SyncEventType.CART_CHANGED);

      expect(handler1).toHaveBeenCalledTimes(1);
      expect(handler2).toHaveBeenCalledTimes(1);
    });

    it("unsubscribe stops delivery", () => {
      const handler = vi.fn();
      const unsub = bus.subscribe(SyncEventType.CART_CHANGED, handler);

      bus.emit(SyncEventType.CART_CHANGED);
      expect(handler).toHaveBeenCalledTimes(1);

      unsub();
      bus.emit(SyncEventType.CART_CHANGED);
      expect(handler).toHaveBeenCalledTimes(1); // not called again
    });
  });

  describe("subscribeAll", () => {
    it("receives all event types", () => {
      const handler = vi.fn();
      bus.subscribeAll(handler);

      bus.emit(SyncEventType.CART_CHANGED);
      bus.emit(SyncEventType.ORDER_CREATED);
      bus.emit(SyncEventType.INVENTORY_CHANGED);

      expect(handler).toHaveBeenCalledTimes(3);
    });
  });

  describe("versioning and stale detection", () => {
    it("increments version per event", () => {
      const handler = vi.fn();
      bus.subscribe(SyncEventType.CART_CHANGED, handler);

      bus.emit(SyncEventType.CART_CHANGED);
      bus.emit(SyncEventType.CART_CHANGED);
      bus.emit(SyncEventType.CART_CHANGED);

      const versions = handler.mock.calls.map(
        (c: any) => (c[0] as SyncEvent).version,
      );
      expect(versions).toEqual([1, 2, 3]);
    });

    it("drop stale events from same origin", () => {
      const handler = vi.fn();
      bus.subscribe(SyncEventType.CART_CHANGED, handler);

      // Emit from "server" origin with version 1
      bus.emitFromServer(SyncEventType.CART_CHANGED);
      expect(handler).toHaveBeenCalledTimes(1);

      // Emit from "server" origin with version 1 again (stale)
      const staleEvent: SyncEvent = {
        type: SyncEventType.CART_CHANGED,
        ts: Date.now(),
        origin: "server",
        version: 1, // same version = stale
      };
      // Use internal dispatch via emitFromServer — but it would create v2
      // So test the version check directly
      const lastVersion = (bus as any)._versions.get("server");
      expect(lastVersion).toBe(1);

      // Simulate receiving stale event by directly calling _dispatch
      (bus as any)._dispatch(staleEvent);
      // Handler should NOT be called again (stale)
      expect(handler).toHaveBeenCalledTimes(1);
    });

    it("allows out-of-order events if version is higher", () => {
      const handler = vi.fn();
      bus.subscribe(SyncEventType.CART_CHANGED, handler);

      // Emit version 3 first (simulating out-of-order)
      const event3: SyncEvent = {
        type: SyncEventType.CART_CHANGED,
        ts: Date.now(),
        origin: "tabB",
        version: 3,
      };
      (bus as any)._dispatch(event3);
      expect(handler).toHaveBeenCalledTimes(1);

      // Emit version 2 (stale — lower than 3)
      const event2: SyncEvent = {
        type: SyncEventType.CART_CHANGED,
        ts: Date.now(),
        origin: "tabB",
        version: 2,
      };
      (bus as any)._dispatch(event2);
      expect(handler).toHaveBeenCalledTimes(1); // not called — stale
    });
  });

  describe("async handlers", () => {
    it("does not throw on async handler errors", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      bus.subscribe(SyncEventType.CART_CHANGED, async () => {
        throw new Error("async handler error");
      });

      // Should not throw
      expect(() => bus.emit(SyncEventType.CART_CHANGED)).not.toThrow();

      // Wait for microtask
      await new Promise((r) => setTimeout(r, 10));

      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });
  });

  describe("destroy", () => {
    it("clears all listeners", () => {
      const handler = vi.fn();
      bus.subscribe(SyncEventType.CART_CHANGED, handler);
      bus.subscribe(SyncEventType.ORDER_CREATED, handler);

      bus.destroy();

      // After destroy, emit should be a no-op
      bus.emit(SyncEventType.CART_CHANGED);
      expect(handler).not.toHaveBeenCalled();
    });
  });
});
