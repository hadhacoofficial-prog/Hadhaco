import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { Copy, RefreshCw } from "lucide-react";
import { toUserMessage } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useDuplicateNotificationTemplate,
  useUpdateNotificationTemplate,
  useWhatsAppTemplateSync,
} from "@/hooks/admin/useNotificationAdmin";
import type { NotificationTemplateOut } from "@hadha/shared-types";

// Example values shown in the Variable Reference Panel so non-technical
// admins understand what a variable represents, not just its raw name.
const VARIABLE_EXAMPLES: Record<string, string> = {
  order_number: "HD-10234",
  total: "1,999",
  amount: "1,999",
  full_name: "Priya Sharma",
  frontend_url: "https://hadha.co",
  tracking_number: "SR123456789IN",
  tracking_url: "https://track.example.com/SR123456789IN",
  awb: "SR123456789IN",
  reason: "Card declined",
  refund_id: "RF-8821",
  old_status: "processing",
  new_status: "shipped",
  sku: "HD-RING-014",
  product_name: "Layla Silver Ring",
  quantity: "3",
};

function extractVariableNames(text: string): string[] {
  const matches = [...text.matchAll(/\{\{\s*([\w.]+)\s*\}\}/g)];
  return [...new Set(matches.map((m) => m[1]))];
}

function renderPreview(text: string, examples: Record<string, string>): string {
  return text.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, name) => examples[name] ?? `[${name}]`);
}

export function TemplateEditor({ template }: { template: NotificationTemplateOut }) {
  const navigate = useNavigate();
  const updateTemplate = useUpdateNotificationTemplate();
  const duplicateTemplate = useDuplicateNotificationTemplate();
  const waSync = useWhatsAppTemplateSync();

  const [subject, setSubject] = useState(template.subject ?? "");
  const [body, setBody] = useState(template.template_body);

  useEffect(() => {
    setSubject(template.subject ?? "");
    setBody(template.template_body);
  }, [template.id, template.subject, template.template_body]);

  const variableNames = useMemo(() => extractVariableNames(`${subject} ${body}`), [subject, body]);

  const isDirty = subject !== (template.subject ?? "") || body !== template.template_body;

  const handleSave = () => {
    updateTemplate.mutate(
      {
        templateId: template.id,
        data: { subject: template.channel === "email" ? subject : undefined, template_body: body },
      },
      {
        onSuccess: () => toast.success("Template saved — a new version was recorded"),
        onError: (e) => toast.error(toUserMessage(e)),
      },
    );
  };

  const handleDuplicate = () => {
    duplicateTemplate.mutate(template.id, {
      onSuccess: (copy) => {
        toast.success("Template duplicated as an inactive draft");
        navigate({
          to: "/admin/notifications/templates/$templateId",
          params: { templateId: copy.id },
        });
      },
      onError: (e) => toast.error(toUserMessage(e)),
    });
  };

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        <div className="bg-background border border-border p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl">
              {template.channel === "email" ? "Email Template" : "WhatsApp Template"}
            </h2>
            <div className="flex items-center gap-2">
              {!template.is_active && (
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground border border-border rounded-full px-2 py-1">
                  Inactive draft
                </span>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={handleDuplicate}
                disabled={duplicateTemplate.isPending}
              >
                <Copy className="size-3.5 mr-1.5" /> Duplicate Template
              </Button>
            </div>
          </div>

          {template.channel === "email" ? (
            <>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Subject</label>
                <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Body (HTML)</label>
                <Textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={16}
                  className="font-mono text-xs"
                />
              </div>
              <div className="flex justify-end">
                <Button onClick={handleSave} disabled={!isDirty || updateTemplate.isPending}>
                  Save Template
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="rounded-md border border-border bg-secondary/40 p-4 text-sm whitespace-pre-wrap">
                {template.template_body}
              </div>
              <div className="text-xs text-muted-foreground">
                Meta template:{" "}
                <span className="font-mono">
                  {(template.variables?.whatsapp_template as string) ?? "(not set)"}
                </span>{" "}
                · Language:{" "}
                <span className="font-mono">
                  {(template.variables?.whatsapp_lang as string) ?? "en_US"}
                </span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => waSync.refetch()}
                disabled={waSync.isFetching}
              >
                <RefreshCw
                  className={`size-3.5 mr-1.5 ${waSync.isFetching ? "animate-spin" : ""}`}
                />
                Sync Templates from Meta
              </Button>
              {waSync.data && (
                <ul className="mt-2 divide-y divide-border border border-border rounded-md text-xs">
                  {waSync.data.length === 0 && (
                    <li className="px-3 py-2 text-muted-foreground">
                      No approved templates found for this WABA.
                    </li>
                  )}
                  {waSync.data.map((t) => (
                    <li
                      key={`${t.name}-${t.language}`}
                      className="px-3 py-2 flex items-center justify-between"
                    >
                      <span className="font-mono">
                        {t.name} ({t.language})
                      </span>
                      <StatusBadge status={t.status} />
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>

        {template.channel === "email" && (
          <div className="bg-background border border-border p-6">
            <h3 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-3">
              Live Preview
            </h3>
            <div className="rounded-md border border-border p-4 space-y-2">
              {subject && (
                <p className="font-medium text-sm">{renderPreview(subject, VARIABLE_EXAMPLES)}</p>
              )}
              <div
                className="text-sm prose-sm max-w-none"
                dangerouslySetInnerHTML={{
                  __html: renderPreview(body, VARIABLE_EXAMPLES),
                }}
              />
            </div>
          </div>
        )}
      </div>

      <div className="bg-background border border-border p-6 h-fit">
        <h3 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-3">
          Variable Reference
        </h3>
        {variableNames.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No <code>{"{{ variable }}"}</code> placeholders found in this template yet.
          </p>
        ) : (
          <ul className="space-y-2 text-xs">
            {variableNames.map((name) => (
              <li key={name} className="flex flex-col gap-0.5">
                <span className="font-mono text-accent">{`{{${name}}}`}</span>
                <span className="text-muted-foreground">
                  e.g. {VARIABLE_EXAMPLES[name] ?? "(example not available)"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    APPROVED: "bg-emerald-50 text-emerald-700",
    PENDING: "bg-amber-50 text-amber-700",
    REJECTED: "bg-red-50 text-red-700",
    DISABLED: "bg-secondary text-muted-foreground",
  };
  return (
    <span
      className={`px-2 py-0.5 rounded-full ${map[status] ?? "bg-secondary text-muted-foreground"}`}
    >
      {status}
    </span>
  );
}
