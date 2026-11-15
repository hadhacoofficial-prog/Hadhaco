import { useEffect, useRef, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";

import { SiteLayout } from "@/components/site/SiteLayout";
import { toUserMessage } from "@/lib/api/errors";
import { useAuthContext } from "@/providers/auth-context";

export const Route = createFileRoute("/account/verify-email")({
  validateSearch: z.object({ token: z.string().optional() }),
  head: () => ({ meta: [{ title: "Verify email · Hadha" }] }),
  component: VerifyEmailPage,
});

function VerifyEmailPage() {
  const { token } = Route.useSearch();
  const navigate = useNavigate();
  const { verifyEmail, resendVerification } = useAuthContext();
  const [email, setEmail] = useState("");
  // The link is single-use: guard against React StrictMode's double effect run.
  const started = useRef(false);

  const verify = useMutation({
    mutationFn: (t: string) => verifyEmail(t),
    onSuccess: (session) => {
      if (session.hasPassword) {
        toast.success("Email verified. Welcome to Hadha!");
        navigate({ to: "/account", replace: true });
      } else {
        // The link was opened in a different browser than the one that
        // registered, so the password chosen at sign-up is not trusted.
        toast.success("Email verified. Please choose a password to finish setting up.");
        navigate({ to: "/account", search: { tab: "security" }, replace: true });
      }
    },
  });

  const resend = useMutation({
    mutationFn: () => resendVerification(email),
    onSuccess: () => toast.success("If that account needs verification, a new link is on its way."),
    onError: (e) => toast.error(toUserMessage(e)),
  });

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    verify.mutate(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const failed = !token || verify.isError;

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-16 max-w-md mx-auto">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground text-center">
          Email verification
        </p>
        <h1 className="font-display text-4xl mt-2 mb-8 text-center">
          {failed ? "Link not valid" : "Verifying…"}
        </h1>

        {failed ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              resend.mutate();
            }}
            className="space-y-5 border border-border bg-card p-8"
          >
            <p className="text-sm text-muted-foreground">
              {verify.isError
                ? toUserMessage(verify.error)
                : "This verification link is incomplete."}{" "}
              Enter your email and we'll send a new one.
            </p>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="Email"
              className="w-full border border-border bg-transparent px-3 py-2.5 text-sm outline-none focus:border-foreground"
            />
            <button
              disabled={resend.isPending}
              className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-60"
            >
              {resend.isPending ? "Sending…" : "Send a new link"}
            </button>
            <p className="text-xs text-center">
              <Link to="/account/login" className="text-accent hover:underline">
                Back to sign in
              </Link>
            </p>
          </form>
        ) : (
          <p className="text-sm text-muted-foreground text-center">
            Confirming your email address, one moment.
          </p>
        )}
      </div>
    </SiteLayout>
  );
}
