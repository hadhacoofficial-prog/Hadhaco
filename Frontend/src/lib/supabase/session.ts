/**
 * Session access helpers.
 *
 * The access token is ALWAYS read from the current Supabase session — never
 * stored or duplicated by the app. Supabase owns persistence + auto-refresh;
 * we just read the freshest token at request time.
 */
import type { Session } from "@supabase/supabase-js";

import { supabase } from "./client";

/** Current session (or null). Reads from Supabase's persisted/refreshed state. */
export async function getSession(): Promise<Session | null> {
  // No window → SSR pass; there is no browser session to read.
  if (typeof window === "undefined") return null;
  const { data } = await supabase.auth.getSession();
  return data.session ?? null;
}

/**
 * Fresh access token for the Authorization header, or null when signed out.
 * Supabase refreshes the token transparently when it is near expiry.
 */
export async function getAccessToken(): Promise<string | null> {
  const session = await getSession();
  return session?.access_token ?? null;
}

/** Authenticated user id (Supabase `sub`), or null. */
export async function getUserId(): Promise<string | null> {
  const session = await getSession();
  return session?.user?.id ?? null;
}
