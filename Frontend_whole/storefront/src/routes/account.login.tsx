import { useState, useEffect } from "react";
import { createFileRoute, useNavigate, Link, redirect } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { Lock, Mail } from "lucide-react";
import { toast } from "sonner";
import { sanitizeRedirect } from "@hadha/shared-utils";

import { SiteLayout } from "@/components/site/SiteLayout";
import { GoogleAuthButton } from "@/components/common/GoogleAuthButton";
import { toUserMessage } from "@/lib/api/errors";
import { getSession } from "@/lib/supabase/session";
import { useAuthContext } from "@/providers/auth-context";

export const Route = createFileRoute("/account/login")({
  validateSearch: z.object({ redirect: z.string().optional() }),
  beforeLoad: async () => {
    if (typeof window === "undefined") return; // SSR: getSession() returns null, skip redirect
    const session = await getSession();
    if (session) throw redirect({ to: "/account" });
  },
  head: () => ({ meta: [{ title: "Sign in · Hadha" }] }),
  component: LoginPage,
});

function LoginPage() {
  const { redirect: redirectTo } = Route.useSearch();
  const navigate = useNavigate();
  const { login, initialized, isAuthenticated } = useAuthContext();

  const safeRedirect = sanitizeRedirect(redirectTo as string | undefined);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Recovery: the server may have redirected an authenticated user here because
  // localStorage is unavailable during SSR and getSession() returned null.
  // Once the client restores the session (initialized=true), bounce back.
  useEffect(() => {
    if (initialized && isAuthenticated) {
      navigate({ to: safeRedirect, replace: true });
    }
  }, [initialized, isAuthenticated, navigate, safeRedirect]);

  const loginMutation = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: () => {
      navigate({ to: safeRedirect });
    },
    onError: (e) => {
      toast.error(toUserMessage(e));
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    loginMutation.mutate();
  };

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-16 max-w-md mx-auto">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground text-center">
          Welcome back
        </p>
        <h1 className="font-display text-4xl mt-2 mb-8 text-center">Sign in</h1>

        <form onSubmit={submit} className="space-y-5 border border-border bg-card p-8">
          <GoogleAuthButton label="Continue with Google" />
          <div className="relative my-1 flex items-center gap-3">
            <span className="flex-1 h-px bg-border" />
            <span className="text-[10px] tracking-[0.32em] uppercase text-muted-foreground">
              or
            </span>
            <span className="flex-1 h-px bg-border" />
          </div>
          <Field
            icon={<Mail className="size-4" />}
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Field
            icon={<Lock className="size-4" />}
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          <div className="flex items-center justify-between text-xs">
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" /> Remember me
            </label>
            <Link to="/account/forgot-password" className="text-accent hover:underline">
              Forgot password?
            </Link>
          </div>

          <button
            disabled={loginMutation.isPending}
            className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-60"
          >
            {loginMutation.isPending ? "Signing in…" : "Sign in"}
          </button>

          <p className="text-xs text-center text-muted-foreground">
            New to Hadha?{" "}
            <Link to="/account/register" className="text-foreground underline">
              Create an account
            </Link>
          </p>
        </form>
      </div>
    </SiteLayout>
  );
}

function Field({
  icon,
  label,
  ...rest
}: { icon: React.ReactNode; label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
      <div className="mt-1.5 flex items-center gap-2 border border-border px-3 focus-within:border-foreground transition">
        <span className="text-muted-foreground">{icon}</span>
        <input {...rest} className="flex-1 bg-transparent py-2.5 text-sm outline-none" />
      </div>
    </label>
  );
}
