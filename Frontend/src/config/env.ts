/**
 * Typed access to client-side env vars. Server-only secrets must NOT
 * be read here — use `process.env.*` inside a `.server.ts` file.
 */
const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

export const ENV = {
  /** FastAPI backend base URL, e.g. `http://localhost:8000/api/v1`. */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_API_BASE_URL,
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
