// k6 helpers — Authentication via Dev Auth endpoint
// Uses POST /api/v1/dev/login to obtain a Supabase JWT
// Only available when ENABLE_DEV_AUTH=true or is_development

import { apiPost, apiUrl } from "./http.js";
import { check, fail } from "k6";

/**
 * Authenticate via the dev login endpoint.
 * Returns { access_token, refresh_token, user_id, email, role } or null.
 *
 * @param {string} email
 * @param {string} password
 * @param {string} role - expected role ("admin", "super_admin", "customer")
 */
export function devLogin(email, password, role) {
  if (!email || !password) {
    fail("Dev auth credentials not set. Set DEV_EMAIL and DEV_PASSWORD env vars.");
    return null;
  }

  const { raw, body } = apiPost("/dev/login", {
    email: email,
    password: password,
  }, {}, { name: "dev_login" });

  check(raw, {
    "dev_login — HTTP 200": (r) => r.status === 200,
    "dev_login — success envelope": (r) => {
      try {
        return JSON.parse(r.body).success === true;
      } catch {
        return false;
      }
    },
  });

  if (!body || !body.data) return null;

  const session = body.data.session;
  const user = body.data.user;

  if (role && user.role !== role) {
    fail(`Expected role '${role}' but got '${user.role}'`);
    return null;
  }

  return {
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    user_id: user.id,
    email: user.email,
    role: user.role,
    expires_at: session.expires_at,
  };
}

/**
 * Generate a unique guest session ID (UUID v4 format).
 * Uses __VU, __ITER, and Date.now() to guarantee uniqueness per VU+iteration.
 * Math.random in k6 is NOT per-VU-seeded, so we must avoid it entirely.
 */
export function generateSessionId() {
  const v = __VU || 0;
  const it = __ITER || 0;
  const ts = Date.now();

  // Deterministic hex from VU/ITER/timestamp — no Math.random
  const seed = (v * 100000 + it) * 1000 + (ts % 1000);
  const s = seed.toString(16).padStart(8, "0");
  const t = ts.toString(16).padStart(12, "0");

  // Build UUID v4 template, fill with deterministic + pseudo-random from seed
  const hex = "0123456789abcdef";
  let uuid = "";
  let idx = 0;
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) {
      uuid += "-";
    } else if (i === 14) {
      uuid += "4"; // version 4
    } else if (i === 19) {
      // variant bits: 8, 9, a, or b
      uuid += hex[8 + (((seed >> (idx * 3)) & 3))];
    } else {
      // Use deterministic chars from our seed/timestamp strings
      const pos = idx % (s.length + t.length);
      const src = pos < s.length ? s : t;
      uuid += src[pos % src.length];
      idx++;
    }
  }
  return uuid;
}

/**
 * Build auth headers for authenticated requests.
 */
export function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

/**
 * Build session headers for guest cart requests.
 */
export function sessionHeaders(sessionId) {
  return {
    "X-Session-ID": sessionId,
    "Content-Type": "application/json",
  };
}
