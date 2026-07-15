import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { getAuthRedirectUrl } from "@hadha/shared-utils";
import { useAuthContext } from "@/providers/auth-context";

interface ProtectedRouteProps {
  children: React.ReactNode;
  /** Path to redirect to when unauthenticated. Defaults to "/account/login". */
  loginPath?: string;
  /** Fallback redirect used when no full-URL capture is possible. Defaults to "/account". */
  defaultRedirect?: string;
}

/**
 * Centralized client-side auth guard.
 *
 * Renders children when authenticated. Redirects to the login page when the
 * session expires after mount (e.g. token refresh fails, user signs out in
 * another tab).
 *
 * This replaces per-component `useSessionGuard()` calls — mount once around
 * any protected content.
 *
 * The `beforeLoad` guard in route definitions handles the initial page-load
 * auth check (before any component mounts). This component handles the
 * "session expires while the user is already on the page" case.
 */
export function ProtectedRoute({
  children,
  loginPath = "/account/login",
  defaultRedirect = "/account",
}: ProtectedRouteProps) {
  const { isAuthenticated, initialized } = useAuthContext();
  const navigate = useNavigate();

  useEffect(() => {
    if (initialized && !isAuthenticated) {
      const redirectUrl = getAuthRedirectUrl(window.location, defaultRedirect);
      navigate({ to: loginPath, search: { redirect: redirectUrl } });
    }
  }, [initialized, isAuthenticated, navigate, loginPath, defaultRedirect]);

  if (!initialized || !isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
