// k6 test — Customer profile and order history
// Tests: GET /me, PATCH /me, GET /orders, GET /orders/{id}
//        GET /me/addresses, POST /me/addresses, DELETE /me/addresses/{id}

import { check, group } from "k6";
import { apiAuthGet, apiAuthPatch, apiAuthPost, apiAuthDelete, think } from "../helpers/http.js";
import { devLogin } from "../helpers/auth.js";
import { loadThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    account_flow: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
    },
  },
  thresholds: loadThresholds,
};

let authCtx = null;

export function setup() {
  const email = __ENV.CUSTOMER_EMAIL;
  const password = __ENV.CUSTOMER_PASSWORD;
  if (email && password) {
    authCtx = devLogin(email, password);
  }
  return { auth: authCtx };
}

export default function (data) {
  const auth = data.auth || authCtx;
  if (!auth || !auth.access_token) return;

  const token = auth.access_token;

  group("Profile", () => {
    const { body } = apiAuthGet("/me", token, {}, { name: "profile_get" });
    check(body, {
      "profile — success": (b) => b && b.success === true,
      "profile — has email": (b) => b && b.data && b.data.email,
    });
    think(0.5);
  });

  group("Orders", () => {
    const { body } = apiAuthGet("/orders", token, {}, { name: "orders_list" });
    check(body, {
      "orders list — success": (b) => b && b.success === true,
      "orders list — has data": (b) => b && b.data && typeof b.data.total === "number",
    });
    think(0.5);

    // Get a specific order if available
    if (body && body.data && body.data.items && body.data.items.length > 0) {
      const order = body.data.items[0];
      const { body: orderDetail } = apiAuthGet(`/orders/${order.id}`, token, {}, {
        name: "order_detail",
      });
      check(orderDetail, {
        "order detail — success": (b) => b && b.success === true,
        "order detail — has items": (b) => b && b.data && b.data.items && b.data.items.length > 0,
      });
      think(0.3);
    }
  });

  group("Addresses", () => {
    const { body: listBody } = apiAuthGet("/me/addresses", token, {}, {
      name: "addresses_list",
    });
    check(listBody, {
      "addresses list — success": (b) => b && b.success === true,
    });
    think(0.3);

    // Create a test address
    const testAddr = {
      type: "shipping",
      full_name: "k6 Test User",
      phone: "+919876543210",
      line1: "123 Test Street",
      city: "Mumbai",
      state: "Maharashtra",
      postal_code: "400001",
      country: "IN",
      is_default: false,
    };

    const { body: createBody } = apiAuthPost("/me/addresses", testAddr, token, {}, {
      name: "address_create",
    });

    if (createBody && createBody.success && createBody.data) {
      check(createBody, {
        "address create — success": (b) => b && b.success === true,
      });
      think(0.3);

      // Delete the test address
      apiAuthDelete(`/me/addresses/${createBody.data.id}`, token, {}, {
        name: "address_delete",
      });
    }
    think(0.3);
  });

  group("Active Reservations", () => {
    const { body } = apiAuthGet("/orders/active-reservations", token, {}, {
      name: "active_reservations",
    });
    check(body, {
      "active reservations — success": (b) => b && b.success === true,
    });
    think(0.3);
  });

  think(1);
}
