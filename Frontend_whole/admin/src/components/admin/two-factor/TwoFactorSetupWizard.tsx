import { useState, useCallback, useEffect } from "react";
import { Copy, Check, Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  InputOTPSeparator,
} from "@/components/ui/input-otp";
import { useTwoFactorSetup, useTwoFactorVerify } from "@/hooks/admin/useTwoFactor";
import { toUserMessage } from "@/lib/api/errors";

type WizardStep = "intro" | "qr" | "verify" | "backup-codes" | "done";

interface TwoFactorSetupWizardProps {
  onComplete: () => void;
  onCancel: () => void;
}

export function TwoFactorSetupWizard({ onComplete, onCancel }: TwoFactorSetupWizardProps) {
  const [step, setStep] = useState<WizardStep>("intro");
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [codesConfirmed, setCodesConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const setupMutation = useTwoFactorSetup();
  const verifyMutation = useTwoFactorVerify();

  const handleStartSetup = useCallback(() => {
    setupMutation.mutate(undefined, {
      onSuccess: (data) => {
        setQrDataUrl(data.qr_code_data_url);
        setSecret(data.secret);
        setStep("qr");
      },
      onError: (e) => setError(toUserMessage(e)),
    });
  }, [setupMutation]);

  const handleVerifyCode = useCallback(() => {
    if (totpCode.length !== 6) return;
    setError(null);
    verifyMutation.mutate(totpCode, {
      onSuccess: (data) => {
        setBackupCodes(data.backup_codes);
        setStep("backup-codes");
      },
      onError: (e) => {
        setError(toUserMessage(e));
        setTotpCode("");
      },
    });
  }, [totpCode, verifyMutation]);

  const handleCopySecret = useCallback(() => {
    if (secret) {
      navigator.clipboard.writeText(secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [secret]);

  const handleCopyBackupCodes = useCallback(() => {
    navigator.clipboard.writeText(backupCodes.join("\n"));
    toast.success("Backup codes copied to clipboard");
  }, [backupCodes]);

  const handleDownloadBackupCodes = useCallback(() => {
    const blob = new Blob([backupCodes.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "hadha-2fa-backup-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }, [backupCodes]);

  const handlePrintBackupCodes = useCallback(() => {
    const win = window.open("", "_blank");
    if (win) {
      win.document.write(
        `<html><head><title>Hadha 2FA Backup Codes</title></head><body>
         <h2>Hadha Admin — 2FA Backup Codes</h2>
         <p>Store these codes securely. Each code can only be used once.</p>
         <pre>${backupCodes.join("\n")}</pre>
         </body></html>`,
      );
      win.document.close();
      win.print();
    }
  }, [backupCodes]);

  useEffect(() => {
    return () => {
      setQrDataUrl(null);
      setSecret(null);
      setBackupCodes([]);
    };
  }, []);

  if (step === "intro") {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold">Set up Two-Factor Authentication</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Add an extra layer of security to your admin account. Once enabled, you'll need to enter
            a code from your authenticator app each time you sign in.
          </p>
        </div>

        <div className="bg-secondary/50 p-4 space-y-2">
          <p className="text-sm font-medium">Supported authenticator apps:</p>
          <ul className="text-sm text-muted-foreground space-y-0.5">
            <li>Google Authenticator</li>
            <li>Microsoft Authenticator</li>
            <li>Authy</li>
            <li>Bitwarden</li>
            <li>1Password</li>
            <li>Aegis</li>
          </ul>
        </div>

        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        <div className="flex gap-3 justify-end">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={handleStartSetup} loading={setupMutation.isPending}>
            Continue
          </Button>
        </div>
      </div>
    );
  }

  if (step === "qr") {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold">Scan QR Code</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Open your authenticator app and scan this QR code.
          </p>
        </div>

        <div className="flex justify-center">
          {qrDataUrl && (
            <img src={qrDataUrl} alt="2FA QR Code" className="w-48 h-48 border border-border" />
          )}
        </div>

        {secret && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Can't scan? Use this setup key instead:</p>
            <div className="flex items-center gap-2 bg-secondary/50 p-3">
              <code className="text-sm font-mono flex-1 break-all">{secret}</code>
              <Button variant="ghost" size="sm" onClick={handleCopySecret}>
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              </Button>
            </div>
          </div>
        )}

        <div className="space-y-3">
          <p className="text-sm font-medium">Enter the 6-digit code from your app:</p>
          <div className="flex justify-center">
            <InputOTP
              maxLength={6}
              value={totpCode}
              onChange={setTotpCode}
              onComplete={handleVerifyCode}
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
        </div>

        {error && (
          <p className="text-sm text-destructive text-center" role="alert">
            {error}
          </p>
        )}

        <div className="flex gap-3 justify-end">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            onClick={handleVerifyCode}
            disabled={totpCode.length !== 6}
            loading={verifyMutation.isPending}
          >
            Verify & Activate
          </Button>
        </div>
      </div>
    );
  }

  if (step === "backup-codes") {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold">Save Your Backup Codes</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Store these codes securely. Each code can only be used once. If you lose access to your
            authenticator, you can use a backup code to sign in.
          </p>
        </div>

        <div className="bg-secondary/50 p-4">
          <div className="grid grid-cols-2 gap-2">
            {backupCodes.map((code, i) => (
              <code key={i} className="text-sm font-mono">
                {code}
              </code>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleCopyBackupCodes}>
            <Copy className="size-3.5 mr-1.5" /> Copy
          </Button>
          <Button variant="outline" size="sm" onClick={handleDownloadBackupCodes}>
            <Download className="size-3.5 mr-1.5" /> Download TXT
          </Button>
          <Button variant="outline" size="sm" onClick={handlePrintBackupCodes}>
            Print
          </Button>
        </div>

        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={codesConfirmed}
            onChange={(e) => setCodesConfirmed(e.target.checked)}
            className="mt-0.5"
          />
          <span className="text-sm">I have safely stored these backup codes.</span>
        </label>

        <div className="flex gap-3 justify-end">
          <Button
            disabled={!codesConfirmed}
            onClick={() => {
              setStep("done");
              onComplete();
            }}
          >
            Finish Setup
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 text-center py-8">
      <div className="mx-auto size-12 rounded-full bg-accent/15 flex items-center justify-center">
        <Check className="size-6 text-accent" />
      </div>
      <h2 className="text-lg font-semibold">Two-Factor Authentication Enabled</h2>
      <p className="text-sm text-muted-foreground">
        Your account is now protected with an additional layer of security.
      </p>
      <Button onClick={onComplete}>Done</Button>
    </div>
  );
}
