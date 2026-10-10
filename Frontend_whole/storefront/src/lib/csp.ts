/**
 * Per-request Content-Security-Policy with a script nonce.
 *
 * TanStack Start's SSR output contains inline <script> tags (stream barrier,
 * dehydration data). Instead of allowing every inline script with
 * 'unsafe-inline', the server mints a nonce per request, hands it to the router
 * (`ssr.nonce`, see router.tsx) so those tags carry it, and sends the matching
 * policy in the response header (see server.ts).
 *
 * The nonce travels from server.ts to getRouter() through an AsyncLocalStorage
 * published on globalThis. server.ts is the only module that imports
 * node:async_hooks, so nothing node-only reaches the client bundle.
 */

export interface CspRequestContext {
  nonce: string;
}

export interface CspContextStore {
  getStore(): CspRequestContext | undefined;
  run<T>(context: CspRequestContext, callback: () => T): T;
}

declare global {
  var __hadhaCspStore: CspContextStore | undefined;
}

/** 128-bit random nonce, base64 encoded (CSP nonce-source grammar). */
export function generateNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

/** Nonce of the request currently being rendered (server only). */
export function currentNonce(): string | undefined {
  return globalThis.__hadhaCspStore?.getStore()?.nonce;
}

/**
 * The storefront policy. Mirrors the previous nginx policy except that
 * script-src no longer allows 'unsafe-inline' / 'unsafe-eval'.
 * style-src keeps 'unsafe-inline': React/Radix/Sonner set inline style
 * attributes at runtime, which a style nonce cannot cover.
 */
export function buildCsp(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' blob: https://static.cloudflareinsights.com https://checkout.razorpay.com https://www.googletagmanager.com`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data: https://fonts.gstatic.com",
    "media-src 'self' https://videos.pexels.com https://cdn.hadha.co",
    "connect-src 'self' https://api.hadha.co https://cdn.hadha.co https://*.supabase.co wss://*.supabase.co https://errors.hadha.co https://*.razorpay.com https://www.google-analytics.com https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com",
    "frame-src 'self' https://api.razorpay.com https://*.razorpay.com",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'self'",
  ].join("; ");
}

export type CspMode = "enforce" | "report-only" | "off";

/**
 * CSP_MODE selects how the policy is delivered (read per request, so changing
 * it only needs a container restart, not a rebuild):
 *   report-only (default) - Content-Security-Policy-Report-Only: violations are
 *                           reported, nothing is blocked. Safe first rollout.
 *   enforce               - Content-Security-Policy: violations are blocked.
 *   off                   - no header from the app (rollback switch).
 * Anything else falls back to report-only.
 */
export function cspMode(env: Record<string, string | undefined> = process.env): CspMode {
  const mode = env.CSP_MODE?.trim().toLowerCase();
  return mode === "enforce" || mode === "off" ? mode : "report-only";
}

/**
 * The header to attach to an HTML response, or null when disabled.
 * CSP_REPORT_URI (optional, e.g. a GlitchTip security endpoint) is appended as
 * report-uri so report-only violations from real browsers are collected.
 */
export function cspHeader(
  nonce: string,
  env: Record<string, string | undefined> = process.env,
): { name: string; value: string } | null {
  const mode = cspMode(env);
  if (mode === "off") return null;
  const reportUri = env.CSP_REPORT_URI?.trim();
  const policy = buildCsp(nonce) + (reportUri ? `; report-uri ${reportUri}` : "");
  return {
    name: mode === "enforce" ? "Content-Security-Policy" : "Content-Security-Policy-Report-Only",
    value: policy,
  };
}
