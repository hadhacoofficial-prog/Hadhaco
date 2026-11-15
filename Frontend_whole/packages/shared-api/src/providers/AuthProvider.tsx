/**
 * AuthProvider — the single source of truth for authentication state.
 *
 * Flow:
 *   App start → ask the backend who the cookies belong to → listen for
 *   changes → expose session/user/role + auth actions to the whole app.
 *
 * Cross-tab session synchronization:
 *   - Uses the centralized sync engine (`afterLogout` / `onSyncEvent`) so
 *     logout, cart, inventory, and other events propagate across tabs
 *     through a single BroadcastChannel ("hadha:sync"). The cookies themselves
 *     are shared by the browser, so a login in one tab only needs the others
 *     to re-read the session.
 */
import type { QueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  changePassword,
  requestPasswordReset,
  resendVerification,
  resetPassword,
  signInWithGoogle,
  signInWithPassword,
  signOut,
  signUpWithPassword,
  verifyEmail,
} from "../lib/auth/actions";
import { getSession, reloadSession } from "../lib/auth/session";
import { setSession, subscribeSession } from "../lib/auth/store";
import type { AuthSession } from "../lib/auth/types";
import {
  afterLogin,
  afterLogout,
  onSyncEvent,
  SyncEventType,
} from "../lib/sync";
import type { AppRole } from "@hadha/shared-types";

import { AuthContext, type AuthContextValue } from "./auth-context";

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
  const [session, setSessionState] = useState<AuthSession | null>(null);
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
      } else if (event === SyncEventType.LOGIN) {
        // Another tab signed in — the cookies are shared, re-read who we are.
        void reloadSession();
      }
    });
    return unsub;
  }, []);

  useEffect(() => {
    mounted.current = true;

    // Every session change (sign-in/out, refresh failure, another tab) funnels
    // through the store, so this is the only place React state is updated.
    const unsubscribe = subscribeSession((s) => {
      if (!mounted.current) return;
      setSessionState(s);
      setRole(s?.user.role ?? null);
      setStatus(s ? "authenticated" : "unauthenticated");
    });

    // Restore the session on boot (no network call for anonymous browsers).
    getSession()
      .then((s) => {
        if (!mounted.current) return;
        setSessionState(s);
        setRole(s?.user.role ?? null);
        setStatus(s ? "authenticated" : "unauthenticated");
        setInitialized(true);
      })
      .catch(() => {
        if (mounted.current) {
          setStatus("unauthenticated");
          setInitialized(true);
        }
      });

    return () => {
      mounted.current = false;
      unsubscribe();
    };
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
        await signInWithPassword(email, password);
        afterLogin();
      },
      register: (name, email, password) =>
        signUpWithPassword(name, email, password),
      verifyEmail: async (token) => {
        const verified = await verifyEmail(token);
        afterLogin();
        return verified;
      },
      resendVerification: (email) => resendVerification(email),
      loginWithGoogle: async (redirectTo) => {
        signInWithGoogle(redirectTo);
      },
      logout: async () => {
        await signOut();
        // Drop the admin 2FA UX flag.
        try {
          sessionStorage.removeItem("hadha:2fa_verified");
        } catch {
          // sessionStorage unavailable (private mode, SSR) — harmless no-op.
        }
        // ── Centralized sync: clears query cache + broadcasts to other tabs ──
        afterLogout();
      },
      requestPasswordReset: (email) => requestPasswordReset(email),
      resetPassword: (token, newPassword) => resetPassword(token, newPassword),
      changePassword: (currentPassword, newPassword) =>
        changePassword(currentPassword, newPassword),
      setRole,
    }),
    [initialized, status, session, role],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
