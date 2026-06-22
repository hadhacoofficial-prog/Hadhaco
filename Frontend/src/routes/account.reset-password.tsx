import { useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { toast } from "sonner";

import { SiteLayout } from "@/components/site/SiteLayout";
import { toUserMessage } from "@/lib/api/errors";
import { useAuthContext } from "@/providers/auth-context";

export const Route = createFileRoute("/account/reset-password")({
  head: () => ({ meta: [{ title: "Reset password · Hadha" }] }),
  component: ResetPasswordPage,
});

function ResetPasswordPage() {
  const { setPassword } = useAuthContext();
  const navigate = useNavigate();
  const [password, setPasswordValue] = useState("");
  const [confirm, setConfirm] = useState("");

  const mutation = useMutation({
    mutationFn: () => {
      if (password !== confirm) throw new Error("Passwords do not match.");
      return setPassword(password);
    },
    onSuccess: () => {
      toast.success("Password updated. Please sign in.");
      navigate({ to: "/account/login" });
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-16 max-w-md mx-auto">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground text-center">
          New password
        </p>
        <h1 className="font-display text-4xl mt-2 mb-8 text-center">Reset password</h1>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
          className="space-y-5 border border-border bg-card p-8"
        >
          <F
            icon={<Lock className="size-4" />}
            label="New password"
            type="password"
            autoComplete="new-password"
            minLength={6}
            value={password}
            onChange={(e) => setPasswordValue(e.target.value)}
            required
          />
          <F
            icon={<Lock className="size-4" />}
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            minLength={6}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
          <button
            disabled={mutation.isPending}
            className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-60"
          >
            {mutation.isPending ? "Updating…" : "Update password"}
          </button>
          <p className="text-xs text-center">
            <Link to="/account/login" className="text-accent hover:underline">
              Back to sign in
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
