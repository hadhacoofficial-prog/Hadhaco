/**
 * AuthProvider — the single source of truth for authentication state.
 *
 * Flow (per integration spec):
 *   App start → restore Supabase session → listen for changes → expose
 *   session/user/role + auth actions to the whole app.
 *
 * Cross-tab session synchronization:
 *   - BroadcastChannel posts "logout" events so other tabs clear state
 *     immediately when the user logs out in one tab.
 *   - An optional QueryClient reference is accepted so that logout clears
 *     all cached API data (prevents stale auth-gated queries).
 */
import type { Session, User } from "@supabase/supabase-js";
import type { QueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  onAuthStateChange,
  resetPasswordForEmail,
  signInWithGoogle,
  signInWithPassword,
  signOut,
  signUpWithPassword,
  updatePassword,
} from "../lib/supabase/auth";
import { getSession } from "../lib/supabase/session";
import type { AppRole } from "@hadha/shared-types";

import { AuthContext, type AuthContextValue } from "./auth-context";

const SYNC_CHANNEL_NAME = "hadha:auth";

/** Provisional role read from Supabase metadata before the backend profile loads. */
function metadataRole(user: User | null): AppRole | null {
  const raw = (user?.app_metadata?.role ?? user?.user_metadata?.role) as string | undefined;
  if (raw === "customer" || raw === "admin" || raw === "super_admin") return raw;
  return null;
}

export interface AuthProviderProps {
  children: ReactNode;
  /**
   * Optional QueryClient reference.
   * When provided, logout will call queryClient.clear() so all cached API
   * data is wiped and no stale auth-gated queries are served.
   */
  queryClient?: QueryClient;
}

export function AuthProvider({ children, queryClient }: AuthProviderProps) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");
  const [role, setRole] = useState<AppRole | null>(null);
  const [initialized, setInitialized] = useState(false);
  const mounted = useRef(true);
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;
  const channelRef = useRef<BroadcastChannel | null>(null);

  // ── Cross-tab synchronization ──────────────────────────────────────────────
  useEffect(() => {
    try {
      channelRef.current = new BroadcastChannel(SYNC_CHANNEL_NAME);
      channelRef.current.onmessage = (event) => {
        if (event.data === "logout") {
          setSession(null);
          setRole(null);
          setStatus("unauthenticated");
          queryClientRef.current?.clear();
        }
      };
    } catch {
      // BroadcastChannel not supported (Safari < 15.4) — graceful degradation.
      // The user will see stale data until they refresh, but no errors.
    }

    return () => {
      channelRef.current?.close();
      channelRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    mounted.current = true;

    // 1) Restore any persisted session on boot.
    getSession()
      .then((s) => {
        if (!mounted.current) return;
        setSession(s);
        setRole(metadataRole(s?.user ?? null));
        setStatus(s ? "authenticated" : "unauthenticated");
        setInitialized(true);
      })
      .catch(() => {
        if (mounted.current) {
          setStatus("unauthenticated");
          setInitialized(true);
        }
      });

    // 2) Subscribe to all future auth transitions (sign-in/out, token refresh).
    const unsubscribe = onAuthStateChange((s) => {
      if (!mounted.current) return;
      setSession(s);
      setRole((prev) => (s ? (prev ?? metadataRole(s.user)) : null));
      setStatus(s ? "authenticated" : "unauthenticated");
    });

    return () => {
      mounted.current = false;
      unsubscribe();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      initialized,
      status,
      isAuthenticated: status === "authenticated",
      session,
      user: session?.user ?? null,
      role,
      login: async (email, password) => {
        const { session: newSession } = await signInWithPassword(email, password);
        // Update context state synchronously instead of waiting for the
        // async onAuthStateChange subscription to catch up — callers that
        // navigate immediately after login() (e.g. the admin login page)
        // would otherwise race a still-"unauthenticated" context against
        // route guards that read isAuthenticated right after the navigate.
        if (mounted.current && newSession) {
          setSession(newSession);
          setRole((prev) => prev ?? metadataRole(newSession.user));
          setStatus("authenticated");
        }
      },
      register: async (name, email, password) => {
        await signUpWithPassword(name, email, password);
      },
      loginWithGoogle: async (redirectTo) => {
        await signInWithGoogle(redirectTo);
      },
      logout: async () => {
        await signOut();
        if (mounted.current) {
          setSession(null);
          setRole(null);
          setStatus("unauthenticated");
        }
        // Drop the admin 2FA UX flag — the backend already invalidates the
        // underlying AdminSession row on logout; this just keeps the client
        // hint in sync so a fresh login always re-runs the challenge.
        try {
          sessionStorage.removeItem("hadha:2fa_verified");
        } catch {
          // sessionStorage unavailable (private mode, SSR) — harmless no-op.
        }
        // ── Centralized React Query cleanup ──────────────────────────────────
        // clear() removes all cached data AND cancels all in-flight queries
        // AND removes all pending mutations AND resets all observer state.
        // This prevents stale auth-gated data from being served and stops
        // any background polling (notifications, inventory, reservations).
        queryClientRef.current?.clear();
        // Notify other tabs to clear their auth state too.
        try {
          channelRef.current?.postMessage("logout");
        } catch {
          // BroadcastChannel unavailable; graceful degradation.
        }
      },
      requestPasswordReset: async (email) => {
        await resetPasswordForEmail(email);
      },
      setPassword: async (newPassword) => {
        await updatePassword(newPassword);
      },
      setRole,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [initialized, status, session, role],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
