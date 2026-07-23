/**
 * AuthProvider — the single source of truth for authentication state.
 *
 * Flow (per integration spec):
 *   App start → restore Supabase session → listen for changes → expose
 *   session/user/role + auth actions to the whole app.
 *
 * Cross-tab session synchronization:
 *   - Uses the centralized sync engine (`afterLogout` / `onSyncEvent`) so
 *     logout, cart, inventory, and other events propagate across tabs
 *     through a single BroadcastChannel ("hadha:sync").
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
import { afterLogout, onSyncEvent, SyncEventType } from "../lib/sync";
import type { AppRole } from "@hadha/shared-types";

import { AuthContext, type AuthContextValue } from "./auth-context";

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

  // ── Cross-tab synchronization via centralized sync engine ──────────────────
  useEffect(() => {
    const unsub = onSyncEvent((event) => {
      if (event === SyncEventType.LOGOUT) {
        setSession(null);
        setRole(null);
        setStatus("unauthenticated");
      } else if (event === SyncEventType.LOGIN) {
        // Another tab logged in — refetch session
        getSession().then((s) => {
          if (!mounted.current) return;
          setSession(s);
          setRole(metadataRole(s?.user ?? null));
          setStatus(s ? "authenticated" : "unauthenticated");
        });
      }
    });
    return unsub;
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
        // Drop the admin 2FA UX flag.
        try {
          sessionStorage.removeItem("hadha:2fa_verified");
        } catch {
          // sessionStorage unavailable (private mode, SSR) — harmless no-op.
        }
        // ── Centralized sync: clears query cache + broadcasts to other tabs ──
        afterLogout();
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
