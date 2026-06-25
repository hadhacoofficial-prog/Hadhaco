/**
 * Typed access to env vars. Works in both SSR (Node.js/Nitro) and browser.
 *
 * apiBaseUrl picks the correct URL for the execution context:
 *   - SSR  â†’ process.env.SERVER_API_BASE_URL (runtime, Docker-internal network)
 *   - Browser â†’ import.meta.env.VITE_API_BASE_URL (baked at build time)
 *
 * This prevents SSR from calling localhost:8000 (unreachable inside the
 * frontend container) or making external HTTPS round-trips through nginx.
 */
const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

const isSsr = typeof window === "undefined";

export const ENV = {
  /** FastAPI backend base URL â€” auto-selected for SSR vs browser context. */
  apiBaseUrl: isSsr
    ? (process.env["SERVER_API_BASE_URL"] ?? DEFAULT_API_BASE_URL)
    : ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_API_BASE_URL),
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL as string | undefined,
  supabasePublishableKey: import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined,
  supabaseProjectId: import.meta.env.VITE_SUPABASE_PROJECT_ID as string | undefined,
  isDev: import.meta.env.DEV,
  isProd: import.meta.env.PROD,
} as const;

/** Returns true when Supabase env is wired up. Used by auth + the repository factory. */
export const hasSupabase = (): boolean => Boolean(ENV.supabaseUrl && ENV.supabasePublishableKey);

/** Returns true when the backend API base URL is configured. */
export const hasApi = (): boolean => Boolean(ENV.apiBaseUrl);
