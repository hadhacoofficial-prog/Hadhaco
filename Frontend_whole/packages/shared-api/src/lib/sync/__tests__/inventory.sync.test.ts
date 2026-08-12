import { describe, expect, it, beforeEach, vi } from "vitest";
import type { Query } from "@tanstack/react-query";

import { SyncBus } from "../SyncBus";
import { SyncEventType } from "../events";
import { registerInventorySync } from "../inventory.sync";

function createMockQueryClient() {
  return {
    invalidateQueries: vi.fn(),
    clear: vi.fn(),
  };
}

type MockQc = ReturnType<typeof createMockQueryClient>;

function findPredicateCall(
  qc: MockQc,
): ((query: Query) => boolean) | undefined {
  const call = qc.invalidateQueries.mock.calls.find(
    (c) =>
      c[0] && typeof (c[0] as { predicate?: unknown }).predicate === "function",
  );
  return call
    ? (call[0] as { predicate: (query: Query) => boolean }).predicate
    : undefined;
}

function findKeyCall(qc: MockQc, key: readonly unknown[]): boolean {
  return qc.invalidateQueries.mock.calls.some((c) => {
    const arg = c[0] as { queryKey?: readonly unknown[] } | undefined;
    if (!arg || !arg.queryKey) return false;
    return (
      arg.queryKey.length === key.length &&
      arg.queryKey.every((v, i) => v === key[i])
    );
  });
}

const q = (queryKey: unknown[], data: unknown): Query =>
  ({ queryKey, state: { data } }) as unknown as Query;

describe("registerInventorySync", () => {
  let qc: MockQc;
  let bus: SyncBus;

  beforeEach(() => {
    qc = createMockQueryClient();
    bus = new SyncBus(qc);
    registerInventorySync(bus);
  });

  it("targets only queries referencing the affected products on INVENTORY_CHANGED", () => {
    bus.emit(SyncEventType.INVENTORY_CHANGED, { productIds: ["p1"] });

    expect(findKeyCall(qc, ["products"])).toBe(false);
    expect(findKeyCall(qc, ["collections"])).toBe(false);
    expect(findKeyCall(qc, ["search"])).toBe(false);
    expect(findKeyCall(qc, ["cms", "homepage"])).toBe(false);
    expect(findKeyCall(qc, ["categories"])).toBe(false);
    // Cart stock stays invalidated (user-scoped, cheap)
    expect(findKeyCall(qc, ["inventory", "cart-stock"])).toBe(true);

    const predicate = findPredicateCall(qc);
    expect(predicate).toBeDefined();

    expect(predicate!(q(["products", "stock", "a"], { id: "p1" }))).toBe(true);
    expect(predicate!(q(["products", "detail", "a"], { id: "p1" }))).toBe(true);
    expect(
      predicate!(q(["products", "list", {}], { items: [{ id: "p1" }] })),
    ).toBe(true);
    expect(predicate!(q(["products", "stock", "b"], { id: "p2" }))).toBe(false);
    expect(
      predicate!(q(["collections", "all"], { items: [{ id: "p1" }] })),
    ).toBe(false);
    expect(
      predicate!(q(["admin", "products", {}], { items: [{ id: "p1" }] })),
    ).toBe(false);
  });

  it("falls back to a coarse products.all bust when no product ids are present", () => {
    bus.emit(SyncEventType.INVENTORY_CHANGED, {});

    expect(findKeyCall(qc, ["products"])).toBe(true);
    expect(findPredicateCall(qc)).toBeUndefined();
  });

  it("keeps a full catalog bust for membership-changing events", () => {
    bus.emit(SyncEventType.PRODUCT_UPDATED, { productId: "p1" });

    expect(findKeyCall(qc, ["products"])).toBe(true);
    expect(findKeyCall(qc, ["collections"])).toBe(true);
    expect(findKeyCall(qc, ["search"])).toBe(true);
    expect(findKeyCall(qc, ["cms", "homepage"])).toBe(true);
    expect(findKeyCall(qc, ["categories"])).toBe(true);
    expect(findKeyCall(qc, ["products", "related", "p1"])).toBe(true);
  });

  it("scopes reservation events by their product ids", () => {
    bus.emit(SyncEventType.RESERVATION_CREATED, {
      reservationId: "r1",
      productIds: ["p1"],
    });

    expect(findKeyCall(qc, ["products"])).toBe(false);
    const predicate = findPredicateCall(qc);
    expect(predicate).toBeDefined();
    expect(predicate!(q(["products", "stock", "a"], { id: "p1" }))).toBe(true);

    qc.invalidateQueries.mockClear();
    bus.emit(SyncEventType.RESERVATION_EXPIRED, {
      reservationId: "r1",
      productIds: ["p2"],
    });
    const predicate2 = findPredicateCall(qc);
    expect(predicate2!(q(["products", "stock", "a"], { id: "p1" }))).toBe(
      false,
    );
    expect(predicate2!(q(["products", "stock", "a"], { id: "p2" }))).toBe(true);
  });
});
