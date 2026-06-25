/**
 * Auth context + hook, separated from the provider component so the provider
 * file only exports a component (keeps React Fast Refresh happy).
 */
import type { Session, User } from "@supabase/supabase-js";
import { createContext, useContext } from "react";

import type { AppRole } from "@hadha/shared-types";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  /** True once the initial getSession() call has resolved (either found or not found). */
  initialized: boolean;
  status: AuthStatus;
  isAuthenticated: boolean;
  session: Session | null;
  user: User | null;
  /** Authoritative role from the backend profile; provisional until loaded. */
  role: AppRole | null;
  // ---- actions ----
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  loginWithGoogle: (redirectTo?: string) => Promise<void>;
  logout: () => Promise<void>;
  requestPasswordReset: (email: string) => Promise<void>;
  setPassword: (newPassword: string) => Promise<void>;
  /** Set the authoritative role once the backend profile is loaded (Phase 1). */
  setRole: (role: AppRole | null) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

/** Access the auth context. Throws if used outside <AuthProvider>. */
export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuthContext must be used within <AuthProvider>");
  return ctx;
}
