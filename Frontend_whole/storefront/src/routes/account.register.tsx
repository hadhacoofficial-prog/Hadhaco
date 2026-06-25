import { useState } from "react";
import { createFileRoute, useNavigate, Link, redirect } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { Lock, Mail, User } from "lucide-react";
import { toast } from "sonner";

import { SiteLayout } from "@/components/site/SiteLayout";
import { GoogleAuthButton } from "@/components/common/GoogleAuthButton";
import { toUserMessage } from "@/lib/api/errors";
import { getSession } from "@/lib/supabase/session";
import { useAuthContext } from "@/providers/auth-context";

export const Route = createFileRoute("/account/register")({
  beforeLoad: async () => {
    const session = await getSession();
    if (session) throw redirect({ to: "/account" });
  },
  head: () => ({ meta: [{ title: "Create account · Hadha" }] }),
  component: RegisterPage,
});

function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuthContext();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const registerMutation = useMutation({
    mutationFn: () => register(name, email, password),
    onSuccess: () => {
      toast.success("Account created! Check your email to confirm, then sign in.");
      navigate({ to: "/account/login" });
    },
    onError: (e) => {
      toast.error(toUserMessage(e));
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    registerMutation.mutate();
  };

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-16 max-w-md mx-auto">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground text-center">
          Join Hadha
        </p>
        <h1 className="font-display text-4xl mt-2 mb-8 text-center">Create your account</h1>

        <form onSubmit={submit} className="space-y-5 border border-border bg-card p-8">
          <GoogleAuthButton label="Sign up with Google" />
          <div className="relative my-1 flex items-center gap-3">
            <span className="flex-1 h-px bg-border" />
            <span className="text-[10px] tracking-[0.32em] uppercase text-muted-foreground">
              or
            </span>
            <span className="flex-1 h-px bg-border" />
          </div>
          <F
            icon={<User className="size-4" />}
            label="Full name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <F
            icon={<Mail className="size-4" />}
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <F
            icon={<Lock className="size-4" />}
            label="Password"
            type="password"
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <p className="text-[11px] text-muted-foreground">
            By creating an account you agree to our Terms & Privacy Policy.
          </p>
          <button
            disabled={registerMutation.isPending}
            className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-60"
          >
            {registerMutation.isPending ? "Creating…" : "Create Account"}
          </button>
          <p className="text-xs text-center text-muted-foreground">
            Already have an account?{" "}
            <Link to="/account/login" className="text-foreground underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </SiteLayout>
  );
}

function F({
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
