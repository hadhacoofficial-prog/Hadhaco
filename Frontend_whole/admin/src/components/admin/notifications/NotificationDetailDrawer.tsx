import DOMPurify from "dompurify";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { RotateCcw } from "lucide-react";
import { useNotificationRules } from "@/hooks/admin/useNotificationAdmin";
import type { NotificationLogOut } from "@hadha/shared-types";

const STATUS_FLOW = ["pending", "retrying", "sent", "delivered", "read", "failed"] as const;

export function NotificationDetailDrawer({
  log,
  onClose,
  onRetry,
  retrying,
}: {
  log: NotificationLogOut | null;
  onClose: () => void;
  onRetry: (logId: string) => void;
  retrying: boolean;
}) {
  const { data: rules } = useNotificationRules();
  const rule = rules?.find((r) => r.event_type === log?.event_type);

  return (
    <Sheet open={!!log} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        {log && (
          <div className="space-y-6">
            <SheetHeader>
              <SheetTitle>{rule?.display_name ?? log.event_type}</SheetTitle>
            </SheetHeader>

            <Section title="Business Event">
              <Row label="Event" value={rule?.display_name ?? log.event_type} />
              <Row label="Category" value={rule?.category ?? "—"} />
              <Row label="Channel" value={log.channel} />
            </Section>

            <Section title="Notification Rule">
              <Row label="Priority" value={rule?.priority ?? "—"} />
              <Row
                label="Retry Policy"
                value={rule?.retry_policy ? JSON.stringify(rule.retry_policy) : "Default"}
              />
              <Row label="Visibility" value={rule?.customer_visible ? "Customer" : "Internal"} />
            </Section>

            <Section title="Lifecycle">
              <div className="flex flex-wrap gap-1.5">
                {STATUS_FLOW.filter((s) => s !== "failed" || log.status === "failed").map((s) => (
                  <span
                    key={s}
                    className={`text-[10px] uppercase tracking-wide px-2 py-1 rounded-full ${
                      log.status === s
                        ? "bg-accent text-accent-foreground"
                        : "bg-secondary text-muted-foreground"
                    }`}
                  >
                    {s}
                  </span>
                ))}
              </div>
            </Section>

            <Section title="Rendered Content">
              <p className="text-xs text-muted-foreground mb-1">Recipient</p>
              <p className="text-sm mb-3">{log.recipient}</p>
              {log.rendered_subject && (
                <>
                  <p className="text-xs text-muted-foreground mb-1">Subject</p>
                  <p className="text-sm mb-3">{log.rendered_subject}</p>
                </>
              )}
              {log.rendered_body && (
                <>
                  <p className="text-xs text-muted-foreground mb-1">Body</p>
                  <div
                    className="text-xs bg-secondary/40 rounded-md p-3 mb-3 max-h-40 overflow-y-auto prose prose-xs max-w-none"
                    dangerouslySetInnerHTML={{
                      __html: DOMPurify.sanitize(log.rendered_body),
                    }}
                  />
                </>
              )}
              {!log.rendered_subject && !log.rendered_body && (
                <>
                  <p className="text-xs text-muted-foreground mb-1">Provider Response</p>
                  <p className="text-sm font-mono break-all">
                    {log.provider_message_id ?? log.error_message ?? "—"}
                  </p>
                </>
              )}
            </Section>

            <Section title="Retry History">
              <Row label="Attempts" value={String(log.attempt_count)} />
              <Row label="Last Error" value={log.error_message ?? "None"} />
            </Section>

            <Section title="Timestamps">
              <Row label="Created" value={new Date(log.created_at).toLocaleString()} />
              {log.sent_at && <Row label="Sent" value={new Date(log.sent_at).toLocaleString()} />}
              {log.delivered_at && (
                <Row label="Delivered" value={new Date(log.delivered_at).toLocaleString()} />
              )}
              {log.read_at && <Row label="Read" value={new Date(log.read_at).toLocaleString()} />}
              {log.failed_at && (
                <Row label="Failed" value={new Date(log.failed_at).toLocaleString()} />
              )}
              {log.template_version && (
                <Row label="Template Version" value={String(log.template_version)} />
              )}
            </Section>

            {log.status === "failed" && (
              <Button
                variant="outline"
                onClick={() => onRetry(log.id)}
                disabled={retrying}
                className="w-full"
              >
                <RotateCcw className="size-3.5 mr-1.5" /> Retry this notification
              </Button>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-2">
        {title}
      </h3>
      <div className="space-y-1 text-sm">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-right break-words">{value}</span>
    </div>
  );
}
