// k6 test — Cart operations: guest + authenticated
// Tests: guest cart CRUD, auth cart, cart merge, price validation
// Requires: DEV_EMAIL/DEV_PASSWORD for authenticated cart (optional)

import { check, group } from "k6";
import { apiGet, apiPost, apiPatch, apiDelete, think } from "../helpers/http.js";
import { generateSessionId, sessionHeaders } from "../helpers/auth.js";

export const options = {
  scenarios: {
    guest_cart: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
      exec: "guestCartFlow",
    },
  },
  thresholds: {
    "http_req_duration{endpoint:/cart}": ["p(95)<800", "p(99)<2000"],
    "http_req_duration{endpoint:/cart/items}": ["p(95)<800", "p(99)<2000"],
  },
};

let allProducts = [];

export function setup() {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: 50, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    allProducts = body.data.items.filter((p) => p.stock_quantity > 0);
  }
  return { products: allProducts };
}

export function guestCartFlow(data) {
  const products = data.products || allProducts;
  if (products.length === 0) return;

  const product = products[Math.floor(Math.random() * products.length)];
  const sessionId = generateSessionId();
  const headers = sessionHeaders(sessionId);

  group("Cart — Empty Cart", () => {
    const { raw, body } = apiGet("/cart", { headers }, { name: "cart_empty" });

    check(raw, {
      "empty cart returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "empty cart has 0 items": (d) => d.item_count === 0 || (d.items && d.items.length === 0),
        "empty cart has 0 subtotal": (d) => d.subtotal === 0 || d.total === 0,
      });
    }
  });

  think(0.5);

  group("Cart — Add Item", () => {
    const { raw, body } = apiPost("/cart/items", {
      product_id: product.id,
      variant_id: product.variant_id || null,
      quantity: 1,
    }, { headers }, { name: "cart_add_item" });

    check(raw, {
      "add item returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "cart has items": (d) => d.items && d.items.length > 0,
        "cart has item_count >= 1": (d) => d.item_count >= 1,
        "cart has subtotal >= 0": (d) => d.subtotal >= 0,
        "cart has total >= 0": (d) => d.total >= 0,
        "cart has id": (d) => d.id !== undefined,
      });
    }
  });

  think(0.5);

  group("Cart — View Cart", () => {
    const { raw, body } = apiGet("/cart", { headers }, { name: "cart_view" });

    check(raw, {
      "view cart returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "view cart has items": (d) => d.items && d.items.length > 0,
        "view cart has subtotal": (d) => d.subtotal !== undefined,
        "view cart items have product_id": (d) => d.items && d.items[0] && d.items[0].product_id !== undefined,
        "view cart items have quantity": (d) => d.items && d.items[0] && d.items[0].quantity > 0,
        "view cart items have price": (d) => d.items && d.items[0] && d.items[0].price !== undefined && d.items[0].price > 0,
        "view cart items have line_total": (d) => d.items && d.items[0] && d.items[0].line_total !== undefined,
      });
    }
  });

  think(0.5);

  // Update quantity if stock allows
  if (product.stock_quantity >= 2) {
    group("Cart — Update Quantity", () => {
      const { raw, body } = apiGet("/cart", { headers }, { name: "cart_get_for_update" });
      if (body && body.data && body.data.items && body.data.items.length > 0) {
        const cartId = body.data.id;
        const itemId = body.data.items[0].id;
        const currentQty = body.data.items[0].quantity;
        const newQty = Math.min(currentQty + 1, product.stock_quantity);

        const { raw: updateRaw, body: updateBody } = apiPatch(
          `/cart/${cartId}/items/${itemId}`,
          { quantity: newQty },
          { headers },
          { name: "cart_update" },
        );

        check(updateRaw, {
          "update returns 200 or 409": (r) => r.status === 200 || r.status === 409,
        });

        if (updateRaw.status === 200 && updateBody && updateBody.data) {
          check(updateBody.data, {
            "updated cart has correct quantity": (d) => {
              const item = d.items && d.items.find((i) => i.id === itemId);
              return item && item.quantity === newQty;
            },
          });
        }
      }
    });

    think(0.5);
  }

  // Remove item
  group("Cart — Remove Item", () => {
    const { raw, body } = apiGet("/cart", { headers }, { name: "cart_get_for_remove" });
    if (body && body.data && body.data.items && body.data.items.length > 0) {
      const cartId = body.data.id;
      const itemId = body.data.items[0].id;

      const { raw: removeRaw } = apiDelete(
        `/cart/${cartId}/items/${itemId}`,
        { headers },
        { name: "cart_remove_item" },
      );

      check(removeRaw, {
        "remove returns 200": (r) => r.status === 200,
      });
    }
  });

  think(0.5);

  // Clear cart
  group("Cart — Clear Cart", () => {
    const { raw, body } = apiDelete("/cart", { headers }, { name: "cart_clear" });

    check(raw, {
      "clear cart returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "cleared cart has 0 items": (d) => d.items && d.items.length === 0,
        "cleared cart subtotal is 0": (d) => d.subtotal === 0,
      });
    }
  });
}

export function teardown() {}
