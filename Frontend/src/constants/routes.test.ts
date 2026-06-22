import { ROUTES } from "./routes";

describe("ROUTES static paths", () => {
  it("home is '/'", () => {
    expect(ROUTES.home).toBe("/");
  });

  it("cart is '/cart'", () => {
    expect(ROUTES.cart).toBe("/cart");
  });

  it("checkout is '/checkout'", () => {
    expect(ROUTES.checkout).toBe("/checkout");
  });

  it("wishlist is '/wishlist'", () => {
    expect(ROUTES.wishlist).toBe("/wishlist");
  });

  it("login is '/account/login'", () => {
    expect(ROUTES.login).toBe("/account/login");
  });

  it("register is '/account/register'", () => {
    expect(ROUTES.register).toBe("/account/register");
  });
});

describe("ROUTES.collection", () => {
  it("interpolates a slug", () => {
    expect(ROUTES.collection("rings")).toBe("/collections/rings");
  });

  it("handles slugs with hyphens", () => {
    expect(ROUTES.collection("new-arrivals")).toBe("/collections/new-arrivals");
  });

  it("handles slugs with numbers", () => {
    expect(ROUTES.collection("925-silver")).toBe("/collections/925-silver");
  });
});

describe("ROUTES.product", () => {
  it("interpolates a slug", () => {
    expect(ROUTES.product("silver-ring")).toBe("/products/silver-ring");
  });

  it("handles long slugs", () => {
    expect(ROUTES.product("925-sterling-silver-filigree-earrings")).toBe(
      "/products/925-sterling-silver-filigree-earrings",
    );
  });
});

describe("ROUTES.admin", () => {
  it("root is '/admin'", () => {
    expect(ROUTES.admin.root).toBe("/admin");
  });

  it("products is '/admin/products'", () => {
    expect(ROUTES.admin.products).toBe("/admin/products");
  });

  it("orders is '/admin/orders'", () => {
    expect(ROUTES.admin.orders).toBe("/admin/orders");
  });
});
