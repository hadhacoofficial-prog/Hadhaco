import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { toast } from "sonner";

import { SiteLayout } from "@/components/site/SiteLayout";
import { toUserMessage } from "@/lib/api/errors";
import { useAuthContext } from "@/providers/auth-context";

export default function ForgotPasswordPage() {
  const { requestPasswordReset } = useAuthContext();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  const mutation = useMutation({
    mutationFn: () => requestPasswordReset(email),
    onSuccess: () => setSent(true),
    onError: (e) => toast.error(toUserMessage(e)),
  });

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-16 max-w-md mx-auto">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground text-center">
          Password reset
        </p>
        <h1 className="font-display text-4xl mt-2 mb-8 text-center">Forgot password?</h1>

        {sent ? (
          <div className="border border-border bg-card p-8 text-center space-y-4">
            <p className="text-sm text-muted-foreground">
              We've sent a reset link to <strong>{email}</strong>. Check your inbox and spam folder.
            </p>
            <Link
              to="/account/login"
              className="inline-block text-[11px] uppercase tracking-[0.22em] text-accent hover:underline"
            >
              Back to sign in
            </Link>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutation.mutate();
            }}
            className="space-y-5 border border-border bg-card p-8"
          >
            <p className="text-sm text-muted-foreground">
              Enter your email and we'll send you a link to reset your password.
            </p>
            <label className="block">
              <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Email
              </span>
              <div className="mt-1.5 flex items-center gap-2 border border-border px-3 focus-within:border-foreground transition">
                <span className="text-muted-foreground">
                  <Mail className="size-4" />
                </span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  className="flex-1 bg-transparent py-2.5 text-sm outline-none"
                />
              </div>
            </label>
            <button
              disabled={mutation.isPending}
              className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-60"
            >
              {mutation.isPending ? "Sending…" : "Send reset link"}
            </button>
            <p className="text-xs text-center">
              <Link to="/account/login" className="text-accent hover:underline">
                Back to sign in
              </Link>
            </p>
          </form>
        )}
      </div>
    </SiteLayout>
  );
}
