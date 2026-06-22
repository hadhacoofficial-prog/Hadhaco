import { useWishlist } from "./wishlist";
import type { WishlistItem } from "./wishlist";

const item1: WishlistItem = {
  id: "p-1",
  slug: "silver-ring",
  name: "Silver Ring",
  image: "https://cdn/ring.jpg",
  price: 999,
  sku: "SR-001",
};

const item2: WishlistItem = {
  id: "p-2",
  slug: "gold-bangle",
  name: "Gold Bangle",
  image: "https://cdn/bangle.jpg",
  price: 2499,
  sku: "GB-001",
};

beforeEach(() => {
  localStorage.clear();
  useWishlist.setState({ items: [] });
});

// ── toggle ────────────────────────────────────────────────────────────────────

describe("wishlist.toggle", () => {
  it("adds an item that is not present", () => {
    useWishlist.getState().toggle(item1);
    expect(useWishlist.getState().items).toHaveLength(1);
    expect(useWishlist.getState().items[0].id).toBe("p-1");
  });

  it("removes an item that is already present", () => {
    useWishlist.getState().toggle(item1);
    useWishlist.getState().toggle(item1);
    expect(useWishlist.getState().items).toHaveLength(0);
  });

  it("treats the same product with different variants as separate entries", () => {
    const v1: WishlistItem = { ...item1, variantId: "v-1" };
    const v2: WishlistItem = { ...item1, variantId: "v-2" };
    useWishlist.getState().toggle(v1);
    useWishlist.getState().toggle(v2);
    expect(useWishlist.getState().items).toHaveLength(2);
  });

  it("removes only the matching variant when toggled off", () => {
    const v1: WishlistItem = { ...item1, variantId: "v-1" };
    const v2: WishlistItem = { ...item1, variantId: "v-2" };
    useWishlist.getState().toggle(v1);
    useWishlist.getState().toggle(v2);
    useWishlist.getState().toggle(v1); // remove v1
    expect(useWishlist.getState().items).toHaveLength(1);
    expect(useWishlist.getState().items[0].variantId).toBe("v-2");
  });

  it("can hold multiple different products", () => {
    useWishlist.getState().toggle(item1);
    useWishlist.getState().toggle(item2);
    expect(useWishlist.getState().items).toHaveLength(2);
  });
});

// ── remove ────────────────────────────────────────────────────────────────────

describe("wishlist.remove", () => {
  it("removes by product id", () => {
    useWishlist.getState().toggle(item1);
    useWishlist.getState().toggle(item2);
    useWishlist.getState().remove("p-1");
    expect(useWishlist.getState().items).toHaveLength(1);
    expect(useWishlist.getState().items[0].id).toBe("p-2");
  });

  it("removes only the matching variant", () => {
    const v1: WishlistItem = { ...item1, variantId: "v-1" };
    const v2: WishlistItem = { ...item1, variantId: "v-2" };
    useWishlist.getState().toggle(v1);
    useWishlist.getState().toggle(v2);
    useWishlist.getState().remove("p-1", "v-1");
    expect(useWishlist.getState().items).toHaveLength(1);
    expect(useWishlist.getState().items[0].variantId).toBe("v-2");
  });
});

// ── has ───────────────────────────────────────────────────────────────────────

describe("wishlist.has", () => {
  it("returns false when the product is not wishlisted", () => {
    expect(useWishlist.getState().has("p-1")).toBe(false);
  });

  it("returns true when the product is wishlisted", () => {
    useWishlist.getState().toggle(item1);
    expect(useWishlist.getState().has("p-1")).toBe(true);
  });

  it("returns true regardless of variant (product-level check)", () => {
    // Any variant of product p-1 makes has("p-1") true
    useWishlist.getState().toggle({ ...item1, variantId: "v-99" });
    expect(useWishlist.getState().has("p-1")).toBe(true);
  });

  it("returns false after the item is removed", () => {
    useWishlist.getState().toggle(item1);
    useWishlist.getState().remove("p-1");
    expect(useWishlist.getState().has("p-1")).toBe(false);
  });
});

// ── clear ─────────────────────────────────────────────────────────────────────

describe("wishlist.clear", () => {
  it("empties the wishlist", () => {
    useWishlist.getState().toggle(item1);
    useWishlist.getState().toggle(item2);
    useWishlist.getState().clear();
    expect(useWishlist.getState().items).toHaveLength(0);
  });
});
