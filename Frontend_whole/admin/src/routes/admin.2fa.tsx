import { createFileRoute, redirect, useNavigate, useSearch } from "@tanstack/react-router";
import { useState, useCallback } from "react";
import { sanitizeRedirect, getAuthRedirectUrl } from "@hadha/shared-utils";
import { useAuthContext } from "@/providers/auth-context";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { getSession } from "@/lib/supabase/session";
import { roleSatisfies } from "@/types/auth";
import type { ProfileDto } from "@/types/profile";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  InputOTPSeparator,
} from "@/components/ui/input-otp";
import { Button } from "@/components/ui/button";
import { useTwoFactorValidate } from "@/hooks/admin/useTwoFactor";
import { toUserMessage } from "@/lib/api/errors";
import logoAsset from "@/assets/hadha-logo.png";
import markAsset from "@/assets/hadha-mark.png";

export const Route = createFileRoute("/admin/2fa")({
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === "string" ? search.redirect : undefined,
  }),
  beforeLoad: async ({ context: { queryClient }, location }) => {
    const session = await getSession();
    if (!session) {
      throw redirect({ to: "/admin/login", search: { redirect: getAuthRedirectUrl(location) } });
    }
    try {
      const profile = await queryClient.fetchQuery({
        queryKey: queryKeys.profile.me,
        queryFn: () => api.get<ProfileDto>("/me"),
        staleTime: 60_000,
      });
      const role = profile?.role;
      const normalizedRole =
        role === "customer" || role === "admin" || role === "super_admin" ? role : null;
      if (!roleSatisfies(normalizedRole, "admin")) {
        throw redirect({ to: "/" });
      }
    } catch (e) {
      if (e && typeof e === "object" && "isRedirect" in e) throw e;
      throw redirect({ to: "/admin/login", search: { redirect: getAuthRedirectUrl(location) } });
    }
  },
  head: () => ({
    meta: [
      { title: "Two-Factor Verification · Hadha Admin" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: TwoFactorChallengePage,
});

function TwoFactorChallengePage() {
  const { redirect: redirectTo } = Route.useSearch();
  const navigate = useNavigate();
  const { logout } = useAuthContext();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [useBackupCode, setUseBackupCode] = useState(false);
  const validateMutation = useTwoFactorValidate();

  const handleVerify = useCallback(() => {
    if (code.length !== 6) return;
    setError(null);
    validateMutation.mutate(code, {
      onSuccess: (res) => {
        if (res.valid) {
          sessionStorage.setItem("hadha:2fa_verified", Date.now().toString());
          const target = sanitizeRedirect(redirectTo, "/admin");
          navigate({ to: target });
        } else {
          setError("Invalid code. Please try again.");
          setCode("");
        }
      },
      onError: (e) => {
        setError(toUserMessage(e));
        setCode("");
      },
    });
  }, [code, validateMutation, redirectTo, navigate]);

  const handleCancel = useCallback(async () => {
    try {
      await logout();
    } finally {
      sessionStorage.removeItem("hadha:2fa_verified");
      navigate({ to: "/admin/login", search: { redirect: undefined } });
    }
  }, [logout, navigate]);

  return (
    <div className="min-h-screen flex">
      {/* Branding panel */}
      <div className="hidden lg:flex lg:w-[400px] xl:w-[480px] bg-foreground text-background flex-col items-center justify-center p-12 shrink-0">
        <img src={logoAsset} alt="Hadha" className="w-52 opacity-90" />
        <p className="mt-3 text-[10px] tracking-[0.36em] uppercase text-background/50">
          Admin Portal
        </p>
        <p className="mt-10 text-sm text-background/40 text-center leading-relaxed max-w-[220px]">
          Two-factor authentication adds an extra layer of security to your account.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex-1 flex flex-col items-center justify-center bg-background px-6 py-12">
        <img src={markAsset} alt="Hadha" className="lg:hidden h-12 mb-10" />

        <div className="w-full max-w-sm">
          <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground mb-1">
            Hadha Admin
          </p>
          <h1 className="font-display text-3xl mb-2">Two-Factor Verification</h1>
          <p className="text-sm text-muted-foreground mb-8">
            {useBackupCode
              ? "Enter one of your backup codes."
              : "Enter the 6-digit code from your authenticator app."}
          </p>

          <div className="flex justify-center mb-6">
            <InputOTP
              maxLength={useBackupCode ? 8 : 6}
              value={code}
              onChange={setCode}
              onComplete={handleVerify}
            >
              <InputOTPGroup>
                {Array.from({ length: useBackupCode ? 8 : 6 })
                  .map((_, i) => <InputOTPSlot key={i} index={i} />)
                  .reduce((acc: React.ReactNode[], slot, i) => {
                    if (useBackupCode) {
                      acc.push(slot);
                      return acc;
                    }
                    if (i > 0 && i % 3 === 0) {
                      acc.push(<InputOTPSeparator key={`sep-${i}`} />);
                    }
                    acc.push(slot);
                    return acc;
                  }, [])}
              </InputOTPGroup>
            </InputOTP>
          </div>

          {error && (
            <p className="text-sm text-destructive text-center mb-4" role="alert">
              {error}
            </p>
          )}

          <Button
            className="w-full"
            onClick={handleVerify}
            disabled={code.length < 6 || validateMutation.isPending}
            loading={validateMutation.isPending}
          >
            {validateMutation.isPending ? "Verifying…" : "Verify"}
          </Button>

          <div className="mt-4 flex flex-col items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setUseBackupCode(!useBackupCode);
                setCode("");
                setError(null);
              }}
              className="text-xs text-muted-foreground hover:text-foreground transition"
            >
              {useBackupCode ? "Use authenticator code instead" : "Use a backup code instead"}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="text-xs text-muted-foreground hover:text-foreground transition"
            >
              Cancel and sign out
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
