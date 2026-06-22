/**
 * AuthProvider — the single source of truth for authentication state.
 *
 * Flow (per integration spec):
 *   App start → restore Supabase session → listen for changes → expose
 *   session/user/role + auth actions to the whole app.
 *
 * The access token itself is never stored here; it always lives in the
 * Supabase session and is read fresh by the HTTP client per request. Role and
 * full profile are layered on in Phase 1 (backend `/me`) via `setRole`.
 */
import type { Session, User } from "@supabase/supabase-js";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  onAuthStateChange,
  resetPasswordForEmail,
  signInWithGoogle,
  signInWithPassword,
  signOut,
  signUpWithPassword,
  updatePassword,
} from "@/lib/supabase/auth";
import { getSession } from "@/lib/supabase/session";
import type { AppRole } from "@/types/auth";

import { AuthContext, type AuthContextValue } from "./auth-context";

/** Provisional role read from Supabase metadata before the backend profile loads. */
function metadataRole(user: User | null): AppRole | null {
  const raw = (user?.app_metadata?.role ?? user?.user_metadata?.role) as string | undefined;
  if (raw === "customer" || raw === "admin" || raw === "super_admin") return raw;
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");
  const [role, setRole] = useState<AppRole | null>(null);
  const [initialized, setInitialized] = useState(false);
  const mounted = useRef(true);

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
      },
      requestPasswordReset: async (email) => {
        await resetPasswordForEmail(email);
      },
      setPassword: async (newPassword) => {
        await updatePassword(newPassword);
      },
      setRole,
    }),
    [initialized, status, session, role],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
