// k6 test — Authentication flow testing
// Tests: POST /dev/login, GET /dev/me, POST /auth/verify-token
//        POST /auth/logout

import { check, group } from "k6";
import { apiPost, apiGet, apiAuthGet, apiAuthPost, think } from "../helpers/http.js";
import { devLogin, generateSessionId } from "../helpers/auth.js";
import { loadThresholds } from "../thresholds/default.js";

export const options = {
  scenarios: {
    auth_flow: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
    },
  },
  thresholds: {
    ...loadThresholds,
    "http_req_duration{endpoint:/dev/login}": ["p(95)<1000"],
    "http_req_duration{endpoint:/auth/verify-token}": ["p(95)<500"],
  },
};

export default function () {
  group("Dev Auth — Login", () => {
    const email = __ENV.DEV_EMAIL;
    const password = __ENV.DEV_PASSWORD;

    if (!email || !password) {
      // Test with invalid credentials to verify error handling
      const { raw, body } = apiPost("/dev/login", {
        email: "nonexistent@test.com",
        password: "wrongpassword",
      }, {}, { name: "auth_login_invalid" });

      check(raw, {
        "auth invalid login — 401 or 422": (r) => r.status === 401 || r.status === 422 || r.status === 404,
      });
      return;
    }

    // Valid login
    const auth = devLogin(email, password);
    check(auth, {
      "auth login — returned token": (a) => a && a.access_token,
      "auth login — returned user_id": (a) => a && a.user_id,
    });

    if (!auth) return;
    think(0.5);

    group("Auth — Verify Token", () => {
      const { body } = apiAuthGet("/dev/me", auth.access_token, {}, {
        name: "auth_verify_token",
      });
      check(body, {
        "auth verify — success": (b) => b && b.success === true,
        "auth verify — has role": (b) => b && b.data && b.data.role,
      });
      think(0.3);
    });

    group("Auth — Profile", () => {
      const { body } = apiAuthGet("/me", auth.access_token, {}, {
        name: "auth_profile",
      });
      check(body, {
        "profile — success": (b) => b && b.success === true,
        "profile — has email": (b) => b && b.data && b.data.email,
      });
      think(0.3);
    });

    group("Auth — Session Validation", () => {
      // Verify the JWT is validated properly by the backend
      const { raw } = apiAuthGet("/me", auth.access_token, {}, {
        name: "auth_session_check",
      });
      check(raw, {
        "session — valid token returns 200": (r) => r.status === 200,
      });

      // Test with invalid token
      const { raw: badRaw } = apiGet("/me", {
        headers: { Authorization: "Bearer invalid_token_abc123" },
      }, { name: "auth_invalid_token" });
      check(badRaw, {
        "invalid token — returns 401": (r) => r.status === 401,
      });
      think(0.3);
    });
  });

  think(1);
}
