import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Laptop, Loader2, ShieldCheck, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  useAdminSessions,
  useRevokeAdminSession,
  useRevokeOtherAdminSessions,
  useRevokeAllAdminSessions,
} from "@/hooks/admin/useAdminSessions";
import { toUserMessage } from "@/lib/api/errors";
import type { AdminSessionOut } from "@hadha/shared-types";

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function expiryLabel(iso: string | null): string {
  if (!iso) return "—";
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return "Expired";
  const totalMins = Math.round(diffMs / 60_000);
  const hours = Math.floor(totalMins / 60);
  const mins = totalMins % 60;
  if (hours < 1) return `Expires in ${mins}m`;
  if (mins === 0) return `Expires in ${hours}h`;
  return `Expires in ${hours}h ${mins}m`;
}

function deviceLabel(session: AdminSessionOut): string {
  const parts = [session.browser_name, session.os_name].filter(Boolean);
  return parts.length ? parts.join(" on ") : "Unknown device";
}

type ConfirmAction = { type: "revoke-others" } | { type: "revoke-all" } | null;

export function ActiveSessionsPanel({ is2faEnabled }: { is2faEnabled: boolean }) {
  const { data, isLoading, isFetching, isError, error, refetch } = useAdminSessions();
  const revokeOne = useRevokeAdminSession();
  const revokeOthers = useRevokeOtherAdminSessions();
  const revokeAll = useRevokeAllAdminSessions();
  const [confirm, setConfirm] = useState<ConfirmAction>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const handleRevokeOne = useCallback(
    (session: AdminSessionOut) => {
      setRevokingId(session.id);
      revokeOne.mutate(session.id, {
        onSuccess: () => toast.success("Session revoked"),
        onError: (e) => toast.error(toUserMessage(e)),
        onSettled: () => setRevokingId(null),
      });
    },
    [revokeOne],
  );

  const handleConfirm = useCallback(() => {
    if (confirm?.type === "revoke-others") {
      revokeOthers.mutate(undefined, {
        onSuccess: (res) => {
          toast.success(`${res.revoked_count} other session(s) signed out`);
          setConfirm(null);
        },
        onError: (e) => {
          toast.error(toUserMessage(e));
          setConfirm(null);
        },
      });
    } else if (confirm?.type === "revoke-all") {
      revokeAll.mutate(undefined, {
        onSuccess: () => {
          toast.success("Signed out everywhere. You'll need to sign in again.");
          setConfirm(null);
          window.location.assign("/admin/login");
        },
        onError: (e) => {
          toast.error(toUserMessage(e));
          setConfirm(null);
        },
      });
    }
  }, [confirm, revokeOthers, revokeAll]);

  if (isLoading) {
    return <Skeleton className="h-40 w-full" />;
  }

  if (isError) {
    return (
      <div className="bg-background border border-border p-6">
        <h3 className="font-semibold">Active Sessions</h3>
        <p className="text-sm text-destructive mt-2">{toUserMessage(error)}</p>
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
    );
  }

  const sessions = data?.sessions ?? [];
  const current = sessions.find((s) => s.is_current);
  const others = sessions.filter((s) => !s.is_current);
  const isConfirming = revokeOthers.isPending || revokeAll.isPending;

  return (
    <div className="bg-background border border-border p-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h3 className="font-semibold">Active Sessions</h3>
        {others.length > 0 && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirm({ type: "revoke-others" })}
            >
              Log Out Other Sessions
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setConfirm({ type: "revoke-all" })}
            >
              Log Out All Sessions
            </Button>
          </div>
        )}
      </div>

      <div className="mt-4 space-y-3">
        {current && <SessionRow session={current} isCurrent />}
        {others.map((session) => (
          <SessionRow
            key={session.id}
            session={session}
            onRevoke={() => handleRevokeOne(session)}
            revoking={revokingId === session.id}
          />
        ))}
        {sessions.length === 0 && (
          <p className="text-sm text-muted-foreground">No active sessions found.</p>
        )}
      </div>

      {others.length > 0 && (
        <p className="text-xs text-muted-foreground mt-4">
          {is2faEnabled ? (
            <>
              "Log out" on another session ends its admin access immediately, but Supabase can only
              fully revoke every session for an account at once — not a single one. If a device may
              be compromised, use "Log Out All Sessions" instead.
            </>
          ) : (
            <>
              2FA is off on this account, so "Log out" here only removes a session from this list —
              it doesn't end that session's access, since there's no per-session check to enforce
              without 2FA. Only "Log Out All Sessions" actually ends access elsewhere (it signs out
              of Supabase directly). Enable two-factor authentication above for real per-device
              control.
            </>
          )}
        </p>
      )}

      <AlertDialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirm?.type === "revoke-all"
                ? "Log out of every session?"
                : "Log out of other sessions?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm?.type === "revoke-all"
                ? is2faEnabled
                  ? "This signs you out of this browser too — you'll need to sign in and complete 2FA again."
                  : "This signs you out of this browser too — you'll need to sign in again."
                : is2faEnabled
                  ? "Every other browser/device currently signed in will need to complete 2FA again to get back in. This one stays signed in."
                  : 'This removes other sessions from this list, but since 2FA is off, it doesn\'t actually end their access — their sign-in stays valid. Use "Log Out All Sessions" to actually sign out everywhere.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirm}
              disabled={isConfirming}
              aria-busy={isConfirming}
            >
              {isConfirming && <Loader2 className="size-4 animate-spin" />}
              {isConfirming ? "Logging out..." : "Confirm"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function SessionRow({
  session,
  isCurrent = false,
  onRevoke,
  revoking = false,
}: {
  session: AdminSessionOut;
  isCurrent?: boolean;
  onRevoke?: () => void;
  revoking?: boolean;
}) {
  return (
    <div className="flex items-center gap-4 py-3 border-b border-border last:border-0">
      <div className="size-9 rounded-lg bg-secondary flex items-center justify-center shrink-0">
        <Laptop className="size-4 text-muted-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium truncate">{deviceLabel(session)}</p>
          {isCurrent && (
            <span className="text-[10px] uppercase tracking-[0.18em] px-1.5 py-0.5 bg-accent/15 text-accent shrink-0">
              This device
            </span>
          )}
          {session.is_2fa_verified ? (
            <ShieldCheck className="size-3.5 text-accent shrink-0" aria-label="2FA verified" />
          ) : (
            <ShieldOff
              className="size-3.5 text-muted-foreground shrink-0"
              aria-label="2FA not verified"
            />
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 truncate">
          {session.last_seen_ip ?? session.ip_address} · Last active{" "}
          {relativeTime(session.last_activity_at ?? session.created_at)} ·{" "}
          {expiryLabel(session.expires_at)}
        </p>
      </div>
      {!isCurrent && onRevoke && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onRevoke}
          loading={revoking}
          aria-label={`Log out ${deviceLabel(session)} session`}
        >
          {revoking ? "Logging out..." : "Log out"}
        </Button>
      )}
    </div>
  );
}
