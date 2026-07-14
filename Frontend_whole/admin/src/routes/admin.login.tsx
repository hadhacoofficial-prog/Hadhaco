import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { sanitizeRedirect } from "@hadha/shared-utils";
import { useAuthContext } from "@/providers/auth-context";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { getSession } from "@/lib/supabase/session";
import { roleSatisfies } from "@/types/auth";
import type { ProfileDto } from "@/types/profile";
import logoAsset from "@/assets/hadha-logo.png";
import markAsset from "@/assets/hadha-mark.png";

// Small helper: wait for Supabase to fully persist the session to localStorage
// before the API client reads it. Without this, api.get() races the SDK's
// internal _saveSession() and goes out without an Authorization header.
function waitForSession(ms = 200): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}

export const Route = createFileRoute("/admin/login")({
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === "string" ? search.redirect : undefined,
  }),
  beforeLoad: async ({ context: { queryClient }, search }) => {
    const session = await getSession();
    if (!session) return; // Not logged in — show the login form

    // Already have a Supabase session — verify admin role
    try {
      const profile = await queryClient.fetchQuery({
        queryKey: queryKeys.profile.me,
        queryFn: () => api.get<ProfileDto>("/me"),
        staleTime: 60_000,
      });
      const role = profile?.role;
      const normalizedRole =
        role === "customer" || role === "admin" || role === "super_admin" ? role : null;
      if (roleSatisfies(normalizedRole, "admin")) {
        // Already an admin — bounce to the sanitized target or dashboard
        throw redirect({ to: sanitizeRedirect(search.redirect, "/admin") });
      }
    } catch (e) {
      // Re-throw TanStack Router redirects
      if (e && typeof e === "object" && "isRedirect" in e) throw e;
      // If /me fails, just show the login form
    }
  },
  head: () => ({
    meta: [{ title: "Admin Login · Hadha" }, { name: "robots", content: "noindex" }],
  }),
  component: AdminLoginPage,
});

function AdminLoginPage() {
  const { redirect: redirectTo } = Route.useSearch();
  const navigate = useNavigate();
  const { login, logout } = useAuthContext();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // 1. Authenticate via Supabase
      await login(email, password);

      // 2. Give the Supabase SDK a tick to persist the session so the API
      //    client can read the token from the freshly-written localStorage entry.
      await waitForSession();

      // 3. Verify this account has admin-level role
      let profile: ProfileDto | null = null;
      try {
        profile = await api.get<ProfileDto>("/me");
      } catch {
        // If the profile fetch fails for any reason, sign out and show an error.
        await logout();
        setError("Unable to verify administrator access. Please try again.");
        return;
      }

      const role = profile?.role;
      const normalizedRole =
        role === "customer" || role === "admin" || role === "super_admin" ? role : null;

      if (!roleSatisfies(normalizedRole, "admin")) {
        await logout();
        setError("This account does not have administrator access.");
        return;
      }

      // 4. Navigate to the originally requested admin page (or dashboard)
      const target = sanitizeRedirect(redirectTo, "/admin");
      navigate({ to: target });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed. Please try again.";
      if (msg.includes("Invalid login credentials") || msg.includes("invalid_credentials")) {
        setError("Invalid email or password.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* ── Branding panel (desktop only) ───────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[400px] xl:w-[480px] bg-foreground text-background flex-col items-center justify-center p-12 shrink-0">
        <img src={logoAsset} alt="Hadha" className="w-52 opacity-90" />
        <p className="mt-3 text-[10px] tracking-[0.36em] uppercase text-background/50">
          Admin Portal
        </p>
        <p className="mt-10 text-sm text-background/40 text-center leading-relaxed max-w-[220px]">
          Manage products, orders, customers, and content from one place.
        </p>
      </div>

      {/* ── Form panel ──────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col items-center justify-center bg-background px-6 py-12">
        {/* Mobile logo */}
        <img src={markAsset} alt="Hadha" className="lg:hidden h-12 mb-10" />

        <div className="w-full max-w-sm">
          <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground mb-1">
            Hadha Admin
          </p>
          <h1 className="font-display text-3xl mb-8">Sign in</h1>

          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            {/* Email */}
            <div className="space-y-1.5">
              <label
                htmlFor="email"
                className="block text-[11px] uppercase tracking-[0.2em] text-muted-foreground"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-border bg-background px-4 py-3 text-sm outline-none focus:border-foreground transition placeholder:text-muted-foreground/40"
                placeholder="admin@hadha.co"
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="block text-[11px] uppercase tracking-[0.2em] text-muted-foreground"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border border-border bg-background px-4 py-3 text-sm outline-none focus:border-foreground transition"
              />
            </div>

            {/* Inline error */}
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-foreground text-background text-[11px] uppercase tracking-[0.22em] py-3.5 hover:opacity-80 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
