// k6 test — Orders and profile management
// Tests: order history, order detail, addresses, wishlist
// Requires: DEV_EMAIL and DEV_PASSWORD environment variables
//
// Without auth: only validates endpoint availability (401 responses)

import { check, group } from "k6";
import { apiGet, apiPost, apiPatch, apiDelete, think } from "../helpers/http.js";

export const options = {
  scenarios: {
    orders: {
      executor: "constant-vus",
      vus: 3,
      duration: "2m",
      exec: "testOrders",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<1000", "p(99)<2500"],
  },
};

export function setup() {
  const email = __ENV.DEV_EMAIL || "";
  const password = __ENV.DEV_PASSWORD || "";
  let token = null;

  if (email && password) {
    const { body: loginBody } = apiPost("/dev/login", {
      email: email,
      password: password,
    }, {}, { name: "setup_login" });

    if (loginBody && loginBody.data && loginBody.data.session) {
      token = loginBody.data.session.access_token;
    }
  }

  return { token: token };
}

export function testOrders(data) {
  const token = data.token;

  if (!token) {
    group("Orders — Unauthenticated", () => {
      const endpoints = [
        { method: "GET", path: "/me" },
        { method: "GET", path: "/orders" },
        { method: "GET", path: "/me/addresses" },
        { method: "GET", path: "/me/wishlist" },
      ];

      endpoints.forEach((ep) => {
        const { raw } = apiGet(ep.path, {}, { name: `orders_unauth_${ep.method}_${ep.path.replace(/\//g, "_")}` });
        check(raw, {
          [`${ep.path} returns 401 without auth`]: (r) => r.status === 401 || r.status === 403,
        });
      });
    });
    return;
  }

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  group("Orders — Profile", () => {
    const { raw, body } = apiGet("/me", { headers }, { name: "orders_profile" });

    check(raw, {
      "profile returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "profile has id": (d) => d.id !== undefined,
        "profile has email": (d) => d.email !== undefined,
        "profile has role": (d) => d.role !== undefined,
      });
    }
  });

  think(0.5);

  group("Orders — Order List", () => {
    const { raw, body } = apiGet("/orders", { headers }, { name: "orders_list" });

    check(raw, {
      "orders list returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "orders has total": (d) => d.total !== undefined,
        "orders has items": (d) => d.items !== undefined,
      });
    }
  });

  think(0.5);

  group("Orders — Active Reservations", () => {
    const { raw, body } = apiGet("/orders/active-reservations", { headers }, {
      name: "orders_reservations",
    });

    check(raw, {
      "reservations returns 200": (r) => r.status === 200,
    });

    if (body) {
      check(body, {
        "reservations success": (b) => b.success === true,
      });
    }
  });

  think(0.5);

  group("Orders — Address List", () => {
    const { raw, body } = apiGet("/me/addresses", { headers }, { name: "orders_addresses" });

    check(raw, {
      "addresses returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "addresses is array": (d) => Array.isArray(d),
      });
    }
  });

  think(0.5);

  // Create and delete an address
  group("Orders — Address CRUD", () => {
    const { raw: createRaw, body: createBody } = apiPost("/me/addresses", {
      full_name: "K6 Test User",
      phone: "9999999999",
      address_line1: "123 Test Street",
      city: "Mumbai",
      state: "Maharashtra",
      pincode: "400001",
      country: "India",
    }, { headers }, { name: "orders_address_create" });

    check(createRaw, {
      "address create returns 200 or 422": (r) => r.status === 200 || r.status === 422,
    });

    if (createRaw.status === 200 && createBody && createBody.data) {
      const addressId = createBody.data.id;

      check(createBody.data, {
        "created address has id": (d) => d.id !== undefined,
        "created address has city": (d) => d.city !== undefined,
      });

      // Set as default
      const { raw: defaultRaw } = apiPost(`/me/addresses/${addressId}/default`, {}, {
        headers,
      }, { name: "orders_address_default" });

      check(defaultRaw, {
        "set default returns 200": (r) => r.status === 200,
      });

      // Delete address
      const { raw: deleteRaw } = apiDelete(`/me/addresses/${addressId}`, {
        headers,
      }, { name: "orders_address_delete" });

      check(deleteRaw, {
        "delete address returns 200": (r) => r.status === 200,
      });
    }
  });

  think(0.5);

  group("Orders — Wishlist", () => {
    const { raw, body } = apiGet("/me/wishlist", { headers }, { name: "orders_wishlist" });

    check(raw, {
      "wishlist returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "wishlist has data": (d) => d !== undefined,
      });
    }
  });

  think(0.5);

  group("Orders — Reviews Endpoint", () => {
    // Just test that the reviews endpoint responds
    const { raw } = apiGet("/reviews/admin/pending", { headers }, {
      name: "orders_reviews_admin",
    });

    // This may return 403 if not admin — that's expected
    check(raw, {
      "reviews endpoint responds": (r) => r.status === 200 || r.status === 403,
    });
  });
}

export function teardown() {}
