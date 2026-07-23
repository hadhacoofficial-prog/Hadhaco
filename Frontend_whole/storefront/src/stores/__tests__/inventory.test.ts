import { describe, it, expect, beforeEach } from "vitest";
import { useInventoryStore, inventoryKey, type InventoryEntry } from "@/stores/inventory";

describe("InventoryStore", () => {
  beforeEach(() => {
    useInventoryStore.getState().clear();
  });

  describe("inventoryKey", () => {
    it("returns productId for base product (no variant)", () => {
      expect(inventoryKey("p1")).toBe("p1");
    });

    it("returns productId::variantId for variant", () => {
      expect(inventoryKey("p1", "v1")).toBe("p1::v1");
    });

    it("uses empty string for null variantId", () => {
      expect(inventoryKey("p1", null)).toBe("p1");
    });
  });

  describe("upsert", () => {
    it("creates a new entry", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 10,
        stockQuantity: 12,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });

      const entry = useInventoryStore.getState().get("p1");
      expect(entry).toBeDefined();
      expect(entry?.availableStock).toBe(10);
      expect(entry?.stockStatus).toBe("in_stock");
    });

    it("derives low_stock status", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 3,
        stockQuantity: 5,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });

      const entry = useInventoryStore.getState().get("p1");
      expect(entry?.stockStatus).toBe("low_stock");
    });

    it("derives sold_out status", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 0,
        stockQuantity: 0,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });

      const entry = useInventoryStore.getState().get("p1");
      expect(entry?.stockStatus).toBe("sold_out");
    });

    it("derives in_stock status when trackInventory is false", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 0,
        stockQuantity: 0,
        lowStockThreshold: 5,
        trackInventory: false,
        allowBackorder: false,
        price: 500,
      });

      const entry = useInventoryStore.getState().get("p1");
      expect(entry?.stockStatus).toBe("in_stock");
    });

    it("derives backorder status", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 0,
        stockQuantity: 5,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: true,
        price: 500,
      });

      const entry = useInventoryStore.getState().get("p1");
      expect(entry?.stockStatus).toBe("backorder");
    });

    it("increments version on every update", () => {
      const v0 = useInventoryStore.getState().version;
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 10,
        stockQuantity: 10,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });
      const v1 = useInventoryStore.getState().version;
      expect(v1).toBe(v0 + 1);
    });
  });

  describe("upsertProduct", () => {
    it("creates base entry and variant entries", () => {
      useInventoryStore.getState().upsertProduct("p1", {
        stock_quantity: 20,
        available_stock: 18,
        low_stock_threshold: 5,
        max_order_quantity: 3,
        track_inventory: true,
        allow_backorder: false,
        base_price: 500,
        variants: [
          { id: "v1", stock_quantity: 10, available_stock: 8, price_adjustment: 100 },
          { id: "v2", stock_quantity: 10, available_stock: 10, price_adjustment: 200 },
        ],
      });

      const base = useInventoryStore.getState().get("p1");
      expect(base).toBeDefined();
      expect(base?.availableStock).toBe(18);
      expect(base?.maxOrderQuantity).toBe(3);

      const v1 = useInventoryStore.getState().get("p1", "v1");
      expect(v1).toBeDefined();
      expect(v1?.availableStock).toBe(8);
      expect(v1?.price).toBe(600); // 500 + 100

      const v2 = useInventoryStore.getState().get("p1", "v2");
      expect(v2).toBeDefined();
      expect(v2?.availableStock).toBe(10);
      expect(v2?.price).toBe(700); // 500 + 200
    });
  });

  describe("optimisticDecrement", () => {
    it("decreases available and increases reserved", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 10,
        stockQuantity: 12,
        reservedQuantity: 2,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });

      useInventoryStore.getState().optimisticDecrement("p1", null, 3);

      const entry = useInventoryStore.getState().get("p1");
      expect(entry?.availableStock).toBe(7);
      expect(entry?.reservedQuantity).toBe(5); // 2 + 3
      expect(entry?.source).toBe("optimistic");
      expect(entry?.confidence).toBe("medium");
    });

    it("does not go below 0", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 2,
        stockQuantity: 5,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });

      useInventoryStore.getState().optimisticDecrement("p1", null, 5);

      const entry = useInventoryStore.getState().get("p1");
      expect(entry?.availableStock).toBe(0);
    });

    it("does nothing if entry does not exist", () => {
      useInventoryStore.getState().optimisticDecrement("nonexistent", null, 1);
      expect(useInventoryStore.getState().get("nonexistent")).toBeUndefined();
    });
  });

  describe("optimisticIncrement", () => {
    it("increases available and decreases reserved", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 7,
        stockQuantity: 12,
        reservedQuantity: 5,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });

      useInventoryStore.getState().optimisticIncrement("p1", null, 3);

      const entry = useInventoryStore.getState().get("p1");
      expect(entry?.availableStock).toBe(10);
      expect(entry?.reservedQuantity).toBe(2); // 5 - 3
    });

    it("reserved does not go below 0", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 7,
        stockQuantity: 12,
        reservedQuantity: 1,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });

      useInventoryStore.getState().optimisticIncrement("p1", null, 5);

      const entry = useInventoryStore.getState().get("p1");
      expect(entry?.reservedQuantity).toBe(0);
    });
  });

  describe("clear", () => {
    it("removes all entries and resets version", () => {
      useInventoryStore.getState().upsert("p1", {
        variantId: null,
        availableStock: 10,
        stockQuantity: 10,
        lowStockThreshold: 5,
        trackInventory: true,
        allowBackorder: false,
        price: 500,
      });
      useInventoryStore.getState().clear();

      expect(useInventoryStore.getState().getAll()).toEqual({});
      expect(useInventoryStore.getState().version).toBe(0);
    });
  });
});

describe("Inventory Selectors", () => {
  beforeEach(() => {
    useInventoryStore.getState().clear();
    useInventoryStore.getState().upsert("p1", {
      variantId: null,
      availableStock: 10,
      stockQuantity: 12,
      lowStockThreshold: 5,
      trackInventory: true,
      allowBackorder: false,
      price: 500,
      stockStatus: "in_stock",
    });
    useInventoryStore.getState().upsert("p1", {
      variantId: "v1",
      availableStock: 2,
      stockQuantity: 5,
      lowStockThreshold: 5,
      trackInventory: true,
      allowBackorder: false,
      price: 600,
      stockStatus: "low_stock",
    });
    useInventoryStore.getState().upsert("p2", {
      variantId: null,
      availableStock: 0,
      stockQuantity: 0,
      lowStockThreshold: 5,
      trackInventory: true,
      allowBackorder: false,
      price: 300,
      stockStatus: "sold_out",
    });
  });

  it("selectAvailableStock returns correct stock", () => {
    const state = useInventoryStore.getState();
    expect(selectAvailableStock("p1")(state)).toBe(10);
    expect(selectAvailableStock("p1", "v1")(state)).toBe(2);
    expect(selectAvailableStock("p2")(state)).toBe(0);
    expect(selectAvailableStock("missing")(state)).toBe(0);
  });

  it("selectStockStatus returns correct status", () => {
    const state = useInventoryStore.getState();
    expect(selectStockStatus("p1")(state)).toBe("in_stock");
    expect(selectStockStatus("p1", "v1")(state)).toBe("low_stock");
    expect(selectStockStatus("p2")(state)).toBe("sold_out");
    expect(selectStockStatus("missing")(state)).toBe("sold_out");
  });

  it("selectIsSoldOut returns correct boolean", () => {
    const state = useInventoryStore.getState();
    expect(selectIsSoldOut("p1")(state)).toBe(false);
    expect(selectIsSoldOut("p2")(state)).toBe(true);
    expect(selectIsSoldOut("missing")(state)).toBe(true);
  });

  it("selectCanAdd respects stock and cartQty", () => {
    const state = useInventoryStore.getState();
    expect(selectCanAdd("p1", null, 0)(state)).toBe(true);
    expect(selectCanAdd("p1", null, 10)(state)).toBe(false); // at max
    expect(selectCanAdd("p2", null, 0)(state)).toBe(false); // sold out
    expect(selectCanAdd("p1", "v1", 0)(state)).toBe(true);
    expect(selectCanAdd("p1", "v1", 2)(state)).toBe(false); // at stock
  });
});

// Import selectors directly for use in tests above
import {
  selectAvailableStock,
  selectStockStatus,
  selectIsSoldOut,
  selectCanAdd,
} from "@/stores/inventory";
