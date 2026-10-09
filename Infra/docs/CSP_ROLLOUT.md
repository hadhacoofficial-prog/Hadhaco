# Storefront CSP: nonce-based script policy

The storefront (`Frontend_whole/storefront`) now sends its own
Content-Security-Policy with a per-request script nonce, so `script-src` no
longer needs `'unsafe-inline'` or `'unsafe-eval'`.

- `src/lib/csp.ts` — nonce generation, policy, mode switch (unit-tested).
- `src/server.ts` — mints the nonce per request, runs the handler inside an
  AsyncLocalStorage, and sets the header on `text/html` responses.
- `src/router.tsx` — passes the nonce to TanStack Start (`ssr.nonce`), which
  stamps it on the inline hydration scripts and the module script.
- `src/lib/error-page.ts` — the inline `onclick` was replaced by a link (inline
  event handlers cannot carry a nonce).

`style-src` still has `'unsafe-inline'` (React/Radix/Sonner set inline `style`
attributes at runtime). `object-src 'none'` and `base-uri 'self'` were added.

## Rollout (nothing changes for users until step 2)

1. **Deploy.** Default `CSP_MODE=report-only`: the app sends
   `Content-Security-Policy-Report-Only`; nginx still enforces the old policy
   (`conf.d/hadha.conf` hides any enforced CSP from the app), so behaviour is
   unchanged. Optionally set `CSP_REPORT_URI` in
   `/opt/hadha/.env.storefront.production` to collect reports.
2. **Enforce.** After a clean soak (including a real test-mode Razorpay payment
   in a browser), set `CSP_MODE=enforce` in `/opt/hadha/.env.storefront.production`
   and restart the storefront container. nginx's old policy and the new one are
   then both enforced; the effective script policy is the strict one.
3. **Clean up nginx.** Remove `proxy_hide_header Content-Security-Policy;` and the
   `add_header Content-Security-Policy ...` line from `conf.d/hadha.conf` so the
   app's header is the only one.

Rollback: `CSP_MODE=off` (or `report-only`) plus a container restart. No rebuild.

## Known, pre-existing

- Razorpay's `checkout.js` tries to load
  `https://cdn.razorpay.com/static/cx/razorpay-risk-detection/bundle.js`. That
  host is not in `script-src` (old or new), so Razorpay's risk-detection script is
  blocked today. Add `https://cdn.razorpay.com` to `script-src` in `csp.ts` if you
  want it; it was left out to keep this change from widening the policy.
- The home page references an Instagram profile URL as a media source, which
  `media-src` blocks (same in the old policy). It looks like a CMS data issue.
