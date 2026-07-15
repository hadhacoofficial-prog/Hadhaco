import { useState, useCallback } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { toast } from "sonner";
import { useTwoFactorStatus } from "@/hooks/admin/useTwoFactor";
import { TwoFactorStatusCard } from "@/components/admin/two-factor/TwoFactorStatus";
import { TwoFactorSetupWizard } from "@/components/admin/two-factor/TwoFactorSetupWizard";
import { ActiveSessionsPanel } from "@/components/admin/security/ActiveSessions";
import { LoginHistoryPanel } from "@/components/admin/security/LoginHistory";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/admin/settings/security")({
  component: SecuritySettingsPage,
});

function SecuritySettingsPage() {
  const { data: status, isLoading, refetch } = useTwoFactorStatus();
  const [showSetup, setShowSetup] = useState(false);

  const handleSetupComplete = useCallback(() => {
    setShowSetup(false);
    toast.success("Two-factor authentication has been enabled");
    refetch();
  }, [refetch]);

  const handleSetupCancel = useCallback(() => {
    setShowSetup(false);
  }, []);

  const handleSetupClick = useCallback(() => {
    setShowSetup(true);
  }, []);

  if (isLoading) {
    return (
      <div>
        <header className="mb-8">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Settings</p>
          <h1 className="font-display text-3xl mt-0.5">Security</h1>
        </header>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Settings</p>
        <h1 className="font-display text-3xl mt-0.5">Security</h1>
      </header>

      {showSetup ? (
        <div className="max-w-xl">
          <TwoFactorSetupWizard onComplete={handleSetupComplete} onCancel={handleSetupCancel} />
        </div>
      ) : (
        <div className="max-w-3xl space-y-6">
          <TwoFactorStatusCard
            status={
              status ?? {
                is_enabled: false,
                enabled_at: null,
                backup_codes_remaining: 0,
                total_backup_codes: 0,
              }
            }
            onSetup={handleSetupClick}
            onStatusChange={() => refetch()}
          />
          <ActiveSessionsPanel is2faEnabled={status?.is_enabled ?? false} />
          <LoginHistoryPanel />
        </div>
      )}
    </div>
  );
}
