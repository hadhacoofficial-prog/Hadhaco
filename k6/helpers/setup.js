// k6 helpers — Reusable test lifecycle setup/teardown

import { devLogin, generateSessionId } from "./auth.js";

/**
 * Setup function for k6 scenarios.
 * Authenticates and returns session context.
 *
 * @param {object} opts
 * @param {string} opts.email - user email
 * @param {string} opts.password - user password
 * @param {string} opts.role - expected role
 * @param {boolean} opts.guest - if true, returns a guest session (no auth)
 * @returns {object} context { token, userId, sessionId, headers }
 */
export function setupSession(opts = {}) {
  const context = {
    token: null,
    userId: null,
    sessionId: generateSessionId(),
    headers: {},
    guestSessionId: generateSessionId(),
  };

  if (!opts.guest && opts.email && opts.password) {
    const auth = devLogin(opts.email, opts.password, opts.role);
    if (auth) {
      context.token = auth.access_token;
      context.userId = auth.user_id;
      context.headers = {
        Authorization: `Bearer ${auth.access_token}`,
        "Content-Type": "application/json",
      };
    }
  }

  context.guestHeaders = {
    "X-Session-ID": context.guestSessionId,
    "Content-Type": "application/json",
  };

  return context;
}
