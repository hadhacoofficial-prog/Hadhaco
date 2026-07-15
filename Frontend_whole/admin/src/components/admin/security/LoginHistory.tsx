import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAdminLoginHistory } from "@/hooks/admin/useAdminSessions";
import { useProfile } from "@/hooks/auth/useProfile";
import { toUserMessage } from "@/lib/api/errors";
import type { AuditLogEntry } from "@hadha/shared-types";

const ACTION_LABELS: Record<string, string> = {
  admin_login: "Signed in",
  admin_logout: "Signed out",
  "2fa_verify_success": "2FA verified",
  "2fa_backup_code_used": "Signed in with a backup code",
  "2fa_verify_failed": "2FA code rejected",
  "2fa_locked_out": "2FA locked (too many attempts)",
  "2fa_enabled": "2FA enabled",
  "2fa_disabled": "2FA disabled",
  "2fa_setup_initiated": "2FA setup started",
  "2fa_backup_codes_regenerated": "Backup codes regenerated",
  admin_session_revoked: "Session revoked",
  admin_sessions_revoked_others: "Other sessions revoked",
  admin_sessions_revoked_all: "All sessions revoked",
  admin_sessions_revoked_on_deactivation: "Sessions revoked (account deactivated)",
  admin_force_logout: "Force-logged out by an admin",
  "2fa_force_reset": "2FA reset by an admin",
};

const FAILURE_ACTIONS = new Set(["2fa_verify_failed", "2fa_locked_out"]);

function actionLabel(entry: AuditLogEntry): string {
  return ACTION_LABELS[entry.action] ?? entry.action.replace(/_/g, " ");
}

export function LoginHistoryPanel() {
  const { data: profile } = useProfile();
  const [page, setPage] = useState(1);
  const [pendingDirection, setPendingDirection] = useState<"prev" | "next" | null>(null);
  const pageSize = 20;
  const { data, isLoading, isFetching, isError, error, refetch } = useAdminLoginHistory(
    profile?.id,
    page,
    pageSize,
  );

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="bg-background border border-border p-6">
      <h3 className="font-semibold">Recent Activity</h3>
      <p className="text-sm text-muted-foreground mt-1">
        Sign-ins, 2FA events, and session changes on your account.
      </p>

      {isLoading ? (
        <Skeleton className="h-40 w-full mt-4" />
      ) : isError ? (
        <div className="mt-4">
          <p className="text-sm text-destructive">{toUserMessage(error)}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            loading={isFetching}
            onClick={() => refetch()}
          >
            Retry
          </Button>
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground mt-4">No activity recorded yet.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>IP Address</TableHead>
                <TableHead>Browser</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>
                    <span
                      className={FAILURE_ACTIONS.has(entry.action) ? "text-destructive" : undefined}
                    >
                      {actionLabel(entry)}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{entry.ip_address ?? "—"}</TableCell>
                  <TableCell
                    className="text-muted-foreground max-w-[220px] truncate"
                    title={entry.user_agent ?? undefined}
                  >
                    {entry.user_agent ?? "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    {new Date(entry.created_at).toLocaleString("en-IN", {
                      day: "numeric",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            loading={isFetching && pendingDirection === "prev"}
            onClick={() => {
              setPendingDirection("prev");
              setPage((p) => Math.max(1, p - 1));
            }}
          >
            Previous
          </Button>
          <span className="text-xs text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            loading={isFetching && pendingDirection === "next"}
            onClick={() => {
              setPendingDirection("next");
              setPage((p) => Math.min(totalPages, p + 1));
            }}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
