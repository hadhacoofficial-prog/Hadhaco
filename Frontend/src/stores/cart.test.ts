import { useCart } from "./cart";
import type { CartProductSnapshot } from "./cart";

const snap: CartProductSnapshot = {
  name: "Silver Ring",
  image: "https://cdn/ring.jpg",
  slug: "silver-ring",
  sku: "SR-001",
  price: 999,
};

beforeEach(() => {
  localStorage.clear();
  useCart.setState({ lines: [], isOpen: false });
});

// ── open / close ──────────────────────────────────────────────────────────────

describe("cart drawer open/close", () => {
  it("opens the cart drawer", () => {
    useCart.getState().open();
    expect(useCart.getState().isOpen).toBe(true);
  });

  it("closes the cart drawer", () => {
    useCart.setState({ isOpen: true });
    useCart.getState().close();
    expect(useCart.getState().isOpen).toBe(false);
  });
});

// ── add ───────────────────────────────────────────────────────────────────────

describe("cart.add", () => {
  it("adds a new line", () => {
    useCart.getState().add("p-1", 1, snap);
    expect(useCart.getState().lines).toHaveLength(1);
    expect(useCart.getState().lines[0].productId).toBe("p-1");
    expect(useCart.getState().lines[0].qty).toBe(1);
  });

  it("defaults qty to 1 when not provided", () => {
    useCart.getState().add("p-1");
    expect(useCart.getState().lines[0].qty).toBe(1);
  });

  it("increments qty when the same product is added again", () => {
    useCart.getState().add("p-1", 1, snap);
    useCart.getState().add("p-1", 2, snap);
    expect(useCart.getState().lines).toHaveLength(1);
    expect(useCart.getState().lines[0].qty).toBe(3);
  });

  it("treats same product with different variant as a separate line", () => {
    useCart.getState().add("p-1", 1, snap, "v-1");
    useCart.getState().add("p-1", 1, snap, "v-2");
    expect(useCart.getState().lines).toHaveLength(2);
  });

  it("opens the drawer on add", () => {
    useCart.setState({ isOpen: false });
    useCart.getState().add("p-1", 1, snap);
    expect(useCart.getState().isOpen).toBe(true);
  });

  it("preserves an existing snapshot when none is passed on the second add", () => {
    useCart.getState().add("p-1", 1, snap);
    useCart.getState().add("p-1", 1); // no snapshot
    expect(useCart.getState().lines[0].snapshot).toEqual(snap);
  });
});

// ── remove ────────────────────────────────────────────────────────────────────

describe("cart.remove", () => {
  it("removes the matching line", () => {
    useCart.getState().add("p-1", 1, snap);
    useCart.getState().add("p-2", 1, snap);
    useCart.getState().remove("p-1");
    const lines = useCart.getState().lines;
    expect(lines).toHaveLength(1);
    expect(lines[0].productId).toBe("p-2");
  });

  it("removes only the matching variant", () => {
    useCart.getState().add("p-1", 1, snap, "v-1");
    useCart.getState().add("p-1", 1, snap, "v-2");
    useCart.getState().remove("p-1", "v-1");
    const lines = useCart.getState().lines;
    expect(lines).toHaveLength(1);
    expect(lines[0].variantId).toBe("v-2");
  });

  it("is a no-op when the product is not in the cart", () => {
    useCart.getState().add("p-1", 1, snap);
    useCart.getState().remove("p-99");
    expect(useCart.getState().lines).toHaveLength(1);
  });
});

// ── setQty ────────────────────────────────────────────────────────────────────

describe("cart.setQty", () => {
  it("updates the quantity of a line", () => {
    useCart.getState().add("p-1", 1, snap);
    useCart.getState().setQty("p-1", 5);
    expect(useCart.getState().lines[0].qty).toBe(5);
  });

  it("removes the line when qty is set to 0", () => {
    useCart.getState().add("p-1", 2, snap);
    useCart.getState().setQty("p-1", 0);
    expect(useCart.getState().lines).toHaveLength(0);
  });

  it("removes the line when qty is set to a negative value", () => {
    useCart.getState().add("p-1", 2, snap);
    useCart.getState().setQty("p-1", -1);
    expect(useCart.getState().lines).toHaveLength(0);
  });
});

// ── clear ─────────────────────────────────────────────────────────────────────

describe("cart.clear", () => {
  it("empties all lines", () => {
    useCart.getState().add("p-1", 1, snap);
    useCart.getState().add("p-2", 2, snap);
    useCart.getState().clear();
    expect(useCart.getState().lines).toHaveLength(0);
  });
});

// ── count ─────────────────────────────────────────────────────────────────────

describe("cart.count", () => {
  it("returns 0 for an empty cart", () => {
    expect(useCart.getState().count()).toBe(0);
  });

  it("returns the total item quantity across all lines", () => {
    useCart.getState().add("p-1", 2, snap);
    useCart.getState().add("p-2", 3, snap);
    expect(useCart.getState().count()).toBe(5);
  });
});

// ── subtotal ──────────────────────────────────────────────────────────────────

describe("cart.subtotal", () => {
  it("returns 0 for an empty cart", () => {
    expect(useCart.getState().subtotal()).toBe(0);
  });

  it("sums price × qty across all lines with snapshots", () => {
    useCart.getState().add("p-1", 2, { ...snap, price: 999 });
    useCart.getState().add("p-2", 1, { ...snap, price: 1499 });
    // 2 × 999 + 1 × 1499 = 3497
    expect(useCart.getState().subtotal()).toBe(3497);
  });

  it("skips lines without a snapshot", () => {
    useCart.getState().add("p-1", 3); // no snapshot → contributes 0
    expect(useCart.getState().subtotal()).toBe(0);
  });
});
