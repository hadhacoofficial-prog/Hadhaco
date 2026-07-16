// k6 test — Complete authentication flow
// Tests: dev login, token verification, profile, logout, invalid token rejection
// Requires: DEV_EMAIL and DEV_PASSWORD environment variables
//
// If credentials are not provided, only the invalid-auth paths are tested.

import { check, group, fail } from "k6";
import { apiGet, apiPost, apiUrl, think } from "../helpers/http.js";
import http from "k6/http";

export const options = {
  scenarios: {
    auth_flow: {
      executor: "constant-vus",
      vus: 3,
      duration: "2m",
      exec: "testAuthFlow",
    },
  },
  thresholds: {
    "http_req_duration{name:auth_login}": ["p(95)<1000"],
    "http_req_duration{name:auth_profile}": ["p(95)<500"],
  },
};

export function testAuthFlow() {
  const email = __ENV.DEV_EMAIL || "";
  const password = __ENV.DEV_PASSWORD || "";

  group("Auth — Invalid Login", () => {
    const { raw, body } = apiPost("/dev/login", {
      email: "nonexistent@test.com",
      password: "wrongpassword",
    }, {}, { name: "auth_login_invalid" });

    check(raw, {
      "invalid login returns 401": (r) => r.status === 401,
    });

    if (body) {
      check(body, {
        "invalid login has error message": (b) => b.message !== undefined || b.success === false,
      });
    }
  });

  think(0.5);

  group("Auth — Empty Body Login", () => {
    const { raw } = apiPost("/dev/login", {}, {}, {
      name: "auth_login_empty",
    });

    check(raw, {
      "empty body login returns error": (r) => r.status >= 400,
    });
  });

  think(0.5);

  if (!email || !password) {
    group("Auth — Skipped (no credentials)", () => {
      check(null, {
        "auth skipped — set DEV_EMAIL/DEV_PASSWORD": () => true,
      });
    });
    return;
  }

  let token = null;

  group("Auth — Valid Login", () => {
    const { raw, body } = apiPost("/dev/login", {
      email: email,
      password: password,
    }, {}, { name: "auth_login" });

    check(raw, {
      "login returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body, {
        "login success": (b) => b.success === true,
        "login has session": (b) => b.data.session !== undefined,
        "login has access_token": (b) => b.data.session && b.data.session.access_token !== undefined,
        "login has user": (b) => b.data.user !== undefined,
        "login has user_id": (b) => b.data.user && b.data.user.id !== undefined,
        "login has email": (b) => b.data.user && b.data.user.email !== undefined,
        "login has role": (b) => b.data.user && b.data.user.role !== undefined,
      });

      token = body.data.session.access_token;
    }
  });

  if (!token) return;

  think(0.5);

  group("Auth — Verify Token", () => {
    const { raw, body } = apiPost("/auth/verify-token", {}, {
      headers: { Authorization: `Bearer ${token}` },
    }, { name: "auth_verify" });

    check(raw, {
      "verify returns 200": (r) => r.status === 200,
    });

    if (body) {
      check(body, {
        "verify success": (b) => b.success === true,
      });
    }
  });

  think(0.5);

  group("Auth — Profile (GET /me)", () => {
    const { raw, body } = apiGet("/me", {
      headers: { Authorization: `Bearer ${token}` },
    }, { name: "auth_profile" });

    check(raw, {
      "profile returns 200": (r) => r.status === 200,
    });

    if (body && body.data) {
      check(body.data, {
        "profile has id": (d) => d && d.id !== undefined,
        "profile has email": (d) => d && d.email !== undefined,
        "profile has role": (d) => d && d.role !== undefined,
      });
    }
  });

  think(0.5);

  group("Auth — Dev Me Endpoint", () => {
    const { raw, body } = apiGet("/dev/me", {
      headers: { Authorization: `Bearer ${token}` },
    }, { name: "auth_dev_me" });

    check(raw, {
      "dev/me returns 200": (r) => r.status === 200,
    });

    if (body) {
      check(body, {
        "dev/me success": (b) => b.success === true,
        "dev/me has user_id": (b) => b.data && b.data.user_id !== undefined,
      });
    }
  });

  think(0.5);

  group("Auth — Expired/Invalid Token", () => {
    const fakeToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c";
    const { raw } = apiGet("/me", {
      headers: { Authorization: `Bearer ${fakeToken}` },
    }, { name: "auth_invalid_token" });

    check(raw, {
      "invalid token returns 401": (r) => r.status === 401 || r.status === 403,
    });
  });

  think(0.5);

  group("Auth — Logout", () => {
    const { raw, body } = apiPost("/auth/logout", {}, {
      headers: { Authorization: `Bearer ${token}` },
    }, { name: "auth_logout" });

    check(raw, {
      "logout returns 200": (r) => r.status === 200,
    });

    if (body) {
      check(body, {
        "logout success": (b) => b.success === true,
      });
    }
  });
}

export function setup() {
  return {};
}

export function teardown() {}
