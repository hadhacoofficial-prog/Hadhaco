/**
 * Auth context + hook, separated from the provider component so the provider
 * file only exports a component (keeps React Fast Refresh happy).
 */
import { createContext, useContext } from "react";

import type { AppRole } from "@hadha/shared-types";

import type { AuthSession, AuthUser, RegisterResult } from "../lib/auth/types";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  /** True once the initial session lookup has resolved (either signed in or not). */
  initialized: boolean;
  status: AuthStatus;
  isAuthenticated: boolean;
  session: AuthSession | null;
  user: AuthUser | null;
  /** Role from the backend session; refined by the profile once loaded. */
  role: AppRole | null;
  // ---- actions ----
  login: (email: string, password: string) => Promise<void>;
  /** Creates the account; the user must verify their email before signing in. */
  register: (
    name: string,
    email: string,
    password: string,
  ) => Promise<RegisterResult>;
  /** Completes the e-mailed verification link and signs the user in. */
  verifyEmail: (token: string) => Promise<AuthSession>;
  resendVerification: (email: string) => Promise<void>;
  loginWithGoogle: (redirectTo?: string) => Promise<void>;
  logout: () => Promise<void>;
  requestPasswordReset: (email: string) => Promise<void>;
  /** Set a new password from the e-mailed reset link. */
  resetPassword: (token: string, newPassword: string) => Promise<void>;
  /** Change the password while signed in (`currentPassword` null for Google-only accounts). */
  changePassword: (
    currentPassword: string | null,
    newPassword: string,
  ) => Promise<void>;
  /** Override the role once the backend profile is loaded. */
  setRole: (role: AppRole | null) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

/** Access the auth context. Throws if used outside <AuthProvider>. */
export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx)
    throw new Error("useAuthContext must be used within <AuthProvider>");
  return ctx;
}
