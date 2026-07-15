import { useCallback, useState } from "react";
import { ShieldCheck, ShieldOff, KeyRound, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  InputOTPSeparator,
} from "@/components/ui/input-otp";
import { useTwoFactorDisable, useTwoFactorRegenerateCodes } from "@/hooks/admin/useTwoFactor";
import { toUserMessage } from "@/lib/api/errors";
import type { TwoFactorStatus } from "@hadha/shared-types";

interface TwoFactorStatusProps {
  status: TwoFactorStatus;
  onSetup: () => void;
  onStatusChange: () => void;
}

export function TwoFactorStatusCard({ status, onSetup, onStatusChange }: TwoFactorStatusProps) {
  const [action, setAction] = useState<"disable" | "regenerate" | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const disableMutation = useTwoFactorDisable();
  const regenerateMutation = useTwoFactorRegenerateCodes();

  const handleConfirm = useCallback(() => {
    if (totpCode.length !== 6) return;
    setError(null);

    if (action === "disable") {
      disableMutation.mutate(totpCode, {
        onSuccess: () => {
          toast.success("Two-factor authentication has been disabled");
          setAction(null);
          setTotpCode("");
          onStatusChange();
        },
        onError: (e) => {
          setError(toUserMessage(e));
          setTotpCode("");
        },
      });
    } else if (action === "regenerate") {
      regenerateMutation.mutate(totpCode, {
        onSuccess: (data) => {
          toast.success("New backup codes generated. Save them — they won't be shown again.");
          setAction(null);
          setTotpCode("");
          onStatusChange();
        },
        onError: (e) => {
          setError(toUserMessage(e));
          setTotpCode("");
        },
      });
    }
  }, [action, totpCode, disableMutation, regenerateMutation, onStatusChange]);

  const handleClose = useCallback(() => {
    setAction(null);
    setTotpCode("");
    setError(null);
  }, []);

  if (!status.is_enabled) {
    return (
      <div className="bg-background border border-border p-6">
        <div className="flex items-start gap-4">
          <div className="size-10 rounded-lg bg-secondary flex items-center justify-center shrink-0">
            <ShieldOff className="size-5 text-muted-foreground" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold">Two-Factor Authentication</h3>
              <span className="text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 bg-secondary text-muted-foreground">
                Disabled
              </span>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              Protect your administrator account with an authenticator application.
            </p>

            <div className="mt-4 space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Supported apps
              </p>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                <span>Google Authenticator</span>
                <span>Microsoft Authenticator</span>
                <span>Authy</span>
                <span>Bitwarden</span>
                <span>1Password</span>
                <span>Aegis</span>
              </div>
            </div>

            <Button onClick={onSetup} className="mt-4">
              Enable Two-Factor Authentication
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="bg-background border border-border p-6">
        <div className="flex items-start gap-4">
          <div className="size-10 rounded-lg bg-accent/15 flex items-center justify-center shrink-0">
            <ShieldCheck className="size-5 text-accent" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold">Two-Factor Authentication</h3>
              <span className="text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 bg-accent/15 text-accent">
                Enabled
              </span>
            </div>

            <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs uppercase tracking-wider">
                  Authenticator
                </p>
                <p className="mt-0.5">Google Authenticator</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs uppercase tracking-wider">Enabled</p>
                <p className="mt-0.5">
                  {status.enabled_at
                    ? new Date(status.enabled_at).toLocaleDateString("en-IN", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })
                    : "—"}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs uppercase tracking-wider">
                  Backup Codes Remaining
                </p>
                <p className="mt-0.5">
                  {status.backup_codes_remaining} / {status.total_backup_codes}
                </p>
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => setAction("regenerate")}>
                <RefreshCw className="size-3.5 mr-1.5" /> Regenerate Backup Codes
              </Button>
              <Button variant="outline" size="sm" onClick={onSetup}>
                <KeyRound className="size-3.5 mr-1.5" /> Change Authenticator Device
              </Button>
              <Button variant="outline" size="sm" onClick={() => setAction("disable")}>
                <ShieldOff className="size-3.5 mr-1.5" /> Disable 2FA
              </Button>
            </div>
          </div>
        </div>
      </div>

      <Dialog
        open={action !== null}
        onOpenChange={(open) => {
          if (!open) handleClose();
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {action === "disable"
                ? "Disable Two-Factor Authentication?"
                : "Regenerate Backup Codes?"}
            </DialogTitle>
            <DialogDescription>
              {action === "disable"
                ? "Your administrator account will no longer require an authenticator app. Enter your current TOTP code to confirm."
                : "All previous backup codes will stop working. Enter your current TOTP code to confirm."}
            </DialogDescription>
          </DialogHeader>

          <div className="flex justify-center py-2">
            <InputOTP
              maxLength={6}
              value={totpCode}
              onChange={setTotpCode}
              onComplete={handleConfirm}
            >
              <InputOTPGroup>
                <InputOTPSlot index={0} />
                <InputOTPSlot index={1} />
                <InputOTPSlot index={2} />
              </InputOTPGroup>
              <InputOTPSeparator />
              <InputOTPGroup>
                <InputOTPSlot index={3} />
                <InputOTPSlot index={4} />
                <InputOTPSlot index={5} />
              </InputOTPGroup>
            </InputOTP>
          </div>

          {error && (
            <p className="text-sm text-destructive text-center" role="alert">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={handleClose}
              disabled={disableMutation.isPending || regenerateMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant={action === "disable" ? "destructive" : "default"}
              disabled={
                totpCode.length !== 6 || disableMutation.isPending || regenerateMutation.isPending
              }
              loading={disableMutation.isPending || regenerateMutation.isPending}
              onClick={handleConfirm}
            >
              {action === "disable" ? "Disable 2FA" : "Generate New Codes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
