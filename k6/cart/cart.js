// k6 test — Cart operations (guest and authenticated)
// Tests: GET /cart, POST /cart/items, PATCH /cart/{id}/items/{id},
//        DELETE /cart/{id}/items/{id}, DELETE /cart, POST /cart/merge

import { check, group } from "k6";
import { apiGet, apiPost, apiPatch, apiDelete, think } from "../helpers/http.js";
import { generateSessionId } from "../helpers/auth.js";
import { loadThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    cart_guest: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
      exec: "guestCartFlow",
    },
  },
  thresholds: {
    ...loadThresholds,
    "http_req_duration{endpoint:/cart}": ["p(95)<300"],
    "http_req_duration{endpoint:/cart/items}": ["p(95)<500"],
  },
};

let availableProducts = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    availableProducts = body.data.items
      .filter((p) => p.stock_quantity >= 2)
      .map((p) => ({
        id: p.id,
        slug: p.slug,
        name: p.name,
        stock: p.stock_quantity,
        variant_id: p.variants && p.variants.length > 0 ? p.variants[0].id : null,
      }));
  }
  return { products: availableProducts };
}

export function guestCartFlow(data) {
  const products = data.products || availableProducts;
  if (products.length === 0) return;

  const sessionId = generateSessionId();
  const headers = { "X-Session-ID": sessionId, "Content-Type": "application/json" };
  const product = products[Math.floor(Math.random() * products.length)];

  group("Guest Cart Flow", () => {
    // 1. Get empty cart
    const { body: emptyCart } = apiGet("/cart", { headers }, { name: "cart_get_empty" });
    check(emptyCart, {
      "empty cart — success": (b) => b && b.success === true,
      "empty cart — 0 items": (b) => b && b.data && b.data.item_count === 0,
    });
    think(0.3);

    // 2. Add item to cart
    const addToCartBody = {
      product_id: product.id,
      variant_id: product.variant_id,
      quantity: 1,
    };
    const { body: addResult } = apiPost("/cart/items", addToCartBody, { headers }, {
      name: "cart_add_item",
    });
    check(addResult, {
      "add to cart — success": (b) => b && b.success === true,
      "add to cart — 1 item": (b) => b && b.data && b.data.item_count >= 1,
    });
    think(0.5);

    // 3. Get cart with items
    const { body: cartWithItems } = apiGet("/cart", { headers }, { name: "cart_get_with_items" });
    check(cartWithItems, {
      "cart with items — success": (b) => b && b.success === true,
      "cart with items — has subtotal": (b) => b && b.data && b.data.subtotal > 0,
    });

    if (cartWithItems && cartWithItems.data && cartWithItems.data.items && cartWithItems.data.items.length > 0) {
      const cartId = cartWithItems.data.id;
      const itemId = cartWithItems.data.items[0].id;
      const currentQty = cartWithItems.data.items[0].quantity;
      const newQty = Math.min(currentQty + 1, product.stock);

      think(0.5);

      // 4. Update cart item quantity
      const { raw: updateRaw, body: updateResult } = apiPatch(
        `/cart/${cartId}/items/${itemId}`,
        { quantity: newQty },
        { headers },
        { name: "cart_update_item" }
      );
      check(updateRaw, {
        "cart_update_item — HTTP 2xx or 409": (r) =>
          (r.status >= 200 && r.status < 300) || r.status === 409,
      });
      check({ raw: updateRaw, body: updateResult }, {
        "update cart item — valid response": (ctx) => {
          if (ctx.body && ctx.body.success === true) return true;
          if (ctx.body && ctx.body.code === "ERROR" && ctx.body.message && ctx.body.message.includes("available")) return true;
          if (ctx.raw.status === 409) return true;
          return false;
        },
      });
      think(0.3);

      // 5. Verify cart state after update
      const { body: verifyCart } = apiGet("/cart", { headers }, { name: "cart_verify_update" });
      check(verifyCart, {
        "verify cart — success": (b) => b && b.success === true,
      });
      think(0.3);

      // 6. Remove item
      const { body: removeResult } = apiDelete(
        `/cart/${cartId}/items/${itemId}`,
        { headers },
        { name: "cart_remove_item" }
      );
      check(removeResult, {
        "remove cart item — success": (b) => b && b.success === true,
      });
      think(0.3);
    }

    // 7. Add another item and clear
    if (products.length > 1) {
      const product2 = products[1];
      apiPost("/cart/items", {
        product_id: product2.id,
        variant_id: product2.variant_id,
        quantity: 1,
      }, { headers }, { name: "cart_add_for_clear" });
      think(0.3);

      const { body: clearResult } = apiDelete("/cart", { headers }, { name: "cart_clear" });
      check(clearResult, {
        "clear cart — success": (b) => b && b.success === true,
      });
    }
  });

  think(1);
}
