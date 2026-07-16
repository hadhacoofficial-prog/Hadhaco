// k6 test — Notification preferences
// Tests: get preferences, update preferences
// Requires: DEV_EMAIL and DEV_PASSWORD environment variables

import { check, group } from "k6";
import { apiGet, apiPut, apiPost, think } from "../helpers/http.js";

export const options = {
  scenarios: {
    notifications: {
      executor: "constant-vus",
      vus: 2,
      duration: "1m",
      exec: "testNotifications",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<500"],
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

export function testNotifications(data) {
  const token = data.token;

  if (!token) {
    group("Notifications — Unauthenticated", () => {
      const { raw } = apiGet("/notifications/preferences", {}, {
        name: "notif_unauth",
      });

      check(raw, {
        "notifications returns 401 without auth": (r) => r.status === 401 || r.status === 403,
      });
    });
    return;
  }

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  group("Notifications — Get Preferences", () => {
    const { raw, body } = apiGet("/notifications/preferences", { headers }, {
      name: "notif_get_prefs",
    });

    check(raw, {
      "get preferences returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "preferences is array": (d) => Array.isArray(d),
      });
    }
  });

  think(0.5);

  group("Notifications — Update Preferences", () => {
    const { raw, body } = apiPut("/notifications/preferences", [
      { event_type: "order_created", channel: "email", enabled: true },
      { event_type: "order_created", channel: "whatsapp", enabled: true },
    ], { headers }, { name: "notif_update_prefs" });

    check(raw, {
      "update preferences returns 200 or 422": (r) => r.status === 200 || r.status === 422,
    });

    if (raw.status === 200 && body) {
      check(body, {
        "update success": (b) => b.success === true,
      });
    }
  });
}

export function teardown() {}
