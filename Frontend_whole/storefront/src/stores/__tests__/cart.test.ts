import { describe, it, expect, beforeEach } from "vitest";
import { useCart } from "@/stores/cart";
import { useInventoryStore } from "@/stores/inventory";

const snapshot = {
  name: "Test Ring",
  image: "/img.jpg",
  slug: "test-ring",
  sku: "SKU-1",
  price: 500,
};

function seedInventory(productId: string, availableStock: number) {
  useInventoryStore.getState().upsert(productId, {
    variantId: null,
    availableStock,
    stockQuantity: availableStock,
    lowStockThreshold: 5,
    trackInventory: true,
    allowBackorder: false,
    price: 500,
  });
}

describe("CartStore optimistic stock sync", () => {
  beforeEach(() => {
    useCart.setState({ lines: [], isOpen: false });
    useInventoryStore.getState().clear();
  });

  it("decrements live stock on add", () => {
    seedInventory("p1", 10);
    useCart.getState().add("p1", 2, snapshot);
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(8);
  });

  it("restores live stock on remove (symmetric with add)", () => {
    seedInventory("p1", 10);
    useCart.getState().add("p1", 3, snapshot);
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(7);

    useCart.getState().remove("p1");
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(10);
  });

  it("restores live stock when setQty reduces quantity", () => {
    seedInventory("p1", 10);
    useCart.getState().add("p1", 5, snapshot);
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(5);

    useCart.getState().setQty("p1", 2);
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(8);
  });

  it("decrements further when setQty increases quantity", () => {
    seedInventory("p1", 10);
    useCart.getState().add("p1", 2, snapshot);
    useCart.getState().setQty("p1", 5);
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(5);
  });

  it("restores full quantity when setQty drops to 0 (removal path)", () => {
    seedInventory("p1", 10);
    useCart.getState().add("p1", 4, snapshot);
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(6);

    useCart.getState().setQty("p1", 0);
    expect(useCart.getState().lines).toHaveLength(0);
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(10);
  });

  it("never leaves stock permanently depleted across an add-then-remove cycle for a low-stock item", () => {
    seedInventory("p1", 1);
    useCart.getState().add("p1", 1, snapshot);
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(0);

    useCart.getState().remove("p1");
    expect(useInventoryStore.getState().get("p1")?.availableStock).toBe(1);
  });
});
