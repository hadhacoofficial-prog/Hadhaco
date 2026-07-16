// k6 test — Wishlist operations (authenticated)
// Tests: GET /me/wishlist, POST /me/wishlist, POST /me/wishlist/toggle,
//        DELETE /me/wishlist/{product_id}

import { check, group } from "k6";
import { apiAuthGet, apiAuthPost, apiAuthDelete, think } from "../helpers/http.js";
import { devLogin } from "../helpers/auth.js";
import { loadThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    wishlist_users: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
    },
  },
  thresholds: loadThresholds,
};

let authCtx = null;
let products = [];

export function setup() {
  const email = __ENV.CUSTOMER_EMAIL;
  const password = __ENV.CUSTOMER_PASSWORD;
  if (email && password) {
    authCtx = devLogin(email, password);
  }

  const { body } = apiAuthGet("/products", authCtx ? authCtx.access_token : "", {
    query: { page: 1, page_size: 10, include_collections: false },
  }, { name: "setup_products" });

  if (body && body.data && body.data.items) {
    products = body.data.items.map((p) => ({ id: p.id, slug: p.slug }));
  }

  return { auth: authCtx, products };
}

export default function (data) {
  const auth = data.auth || authCtx;
  if (!auth || !auth.access_token) return;

  const token = auth.access_token;
  const prods = data.products || products;
  if (prods.length === 0) return;

  const product = prods[Math.floor(Math.random() * prods.length)];

  group("Wishlist", () => {
    // Get wishlist
    const { body: wlBody } = apiAuthGet("/me/wishlist", token, {}, {
      name: "wishlist_get",
    });
    check(wlBody, {
      "wishlist get — success": (b) => b && b.success === true,
    });
    think(0.3);

    // Toggle item in wishlist
    const { body: toggleBody } = apiAuthPost("/me/wishlist/toggle", {
      product_id: product.id,
    }, token, {}, { name: "wishlist_toggle" });

    check(toggleBody, {
      "wishlist toggle — success": (b) => b && b.success === true,
    });
    think(0.3);

    // Toggle again (should remove)
    apiAuthPost("/me/wishlist/toggle", {
      product_id: product.id,
    }, token, {}, { name: "wishlist_toggle_remove" });
    think(0.3);

    // Direct add
    const { body: addBody } = apiAuthPost("/me/wishlist", {
      product_id: product.id,
    }, token, {}, { name: "wishlist_add" });
    check(addBody, {
      "wishlist add — success": (b) => b && b.success === true,
    });
    think(0.3);

    // Direct remove
    apiAuthDelete(`/me/wishlist/${product.id}`, token, {}, {
      name: "wishlist_remove",
    });
    think(0.3);
  });

  think(0.5);
}
