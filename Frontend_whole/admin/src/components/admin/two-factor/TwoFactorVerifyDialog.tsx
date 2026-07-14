import { useState, useCallback } from "react";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  InputOTPSeparator,
} from "@/components/ui/input-otp";
import { Button } from "@/components/ui/button";
import { useTwoFactorValidate } from "@/hooks/admin/useTwoFactor";
import { toUserMessage } from "@/lib/api/errors";

interface TwoFactorVerifyDialogProps {
  onSuccess: () => void;
  onCancel?: () => void;
  title?: string;
  description?: string;
}

export function TwoFactorVerifyDialog({
  onSuccess,
  onCancel,
  title = "Verify your identity",
  description = "Enter the 6-digit code from your authenticator app.",
}: TwoFactorVerifyDialogProps) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const validateMutation = useTwoFactorValidate();

  const handleVerify = useCallback(() => {
    if (code.length !== 6) return;
    setError(null);
    validateMutation.mutate(code, {
      onSuccess: (res) => {
        if (res.valid) {
          onSuccess();
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
  }, [code, validateMutation, onSuccess]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground mt-1">{description}</p>
      </div>

      <div className="flex justify-center">
        <InputOTP maxLength={6} value={code} onChange={setCode} onComplete={handleVerify}>
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

      <div className="flex gap-3 justify-end">
        {onCancel && (
          <Button variant="outline" onClick={onCancel} disabled={validateMutation.isPending}>
            Cancel
          </Button>
        )}
        <Button
          onClick={handleVerify}
          disabled={code.length !== 6 || validateMutation.isPending}
          loading={validateMutation.isPending}
        >
          Verify
        </Button>
      </div>
    </div>
  );
}
