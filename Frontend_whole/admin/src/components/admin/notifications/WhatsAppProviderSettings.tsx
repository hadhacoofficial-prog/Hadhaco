import { useState } from "react";
import { toast } from "sonner";
import { Send, Copy } from "lucide-react";
import { toUserMessage } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { FormSkeleton } from "@/components/loading/FormSkeleton";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useProviderHealth,
  useProviderSettings,
  useTestWhatsAppProvider,
  useUpdateProviderSettings,
} from "@/hooks/admin/useNotificationAdmin";
import { StatusPill } from "./EmailProviderSettings";

export function WhatsAppProviderSettings() {
  const { data: settings, isLoading } = useProviderSettings("whatsapp");
  const { data: health } = useProviderHealth("whatsapp");
  const update = useUpdateProviderSettings("whatsapp");
  const testWhatsApp = useTestWhatsAppProvider();

  const [form, setForm] = useState<Record<string, string>>({});
  const [testOpen, setTestOpen] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [testTemplate, setTestTemplate] = useState("");

  const value = (key: string) => form[key] ?? settings?.settings[key] ?? "";

  const handleSave = () => {
    update.mutate(form, {
      onSuccess: () => {
        toast.success("WhatsApp settings updated");
        setForm({});
      },
      onError: (e) => toast.error(toUserMessage(e)),
    });
  };

  const handleTestSend = () => {
    testWhatsApp.mutate(
      { to: testTo, templateName: testTemplate },
      {
        onSuccess: (result) => {
          if (result.success) toast.success(result.message);
          else toast.error(result.message);
          setTestOpen(false);
        },
        onError: (e) => toast.error(toUserMessage(e)),
      },
    );
  };

  const copyWebhookUrl = () => {
    if (!health?.webhook_url) return;
    navigator.clipboard.writeText(health.webhook_url);
    toast.success("Webhook URL copied");
  };

  if (isLoading) {
    return <FormSkeleton fields={7} columns={1} />;
  }

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 bg-background border border-border p-6 space-y-4">
        <div className="flex items-center justify-between">
          <Label htmlFor="whatsapp-enabled" className="text-sm">
            Enable WhatsApp Notifications
          </Label>
          <Switch
            id="whatsapp-enabled"
            checked={value("enabled") !== "false"}
            onCheckedChange={(checked) => setForm((f) => ({ ...f, enabled: String(checked) }))}
          />
        </div>

        <Field
          label="Business Phone Number"
          value={value("business_phone")}
          onChange={(v) => setForm((f) => ({ ...f, business_phone: v }))}
        />
        <Field
          label="Phone Number ID"
          value={value("phone_number_id")}
          onChange={(v) => setForm((f) => ({ ...f, phone_number_id: v }))}
        />
        <Field
          label="WhatsApp Business Account ID (WABA)"
          value={value("waba_id")}
          onChange={(v) => setForm((f) => ({ ...f, waba_id: v }))}
        />
        <Field
          label="API Version"
          value={value("api_version")}
          placeholder="v21.0"
          onChange={(v) => setForm((f) => ({ ...f, api_version: v }))}
        />
        <Field
          label="Access Token"
          type="password"
          placeholder={settings?.settings.access_token ?? "Not set"}
          value={form.access_token ?? ""}
          onChange={(v) => setForm((f) => ({ ...f, access_token: v }))}
        />
        <Field
          label="Verify Token"
          value={value("verify_token")}
          onChange={(v) => setForm((f) => ({ ...f, verify_token: v }))}
        />
        <Field
          label="Webhook Secret"
          type="password"
          placeholder={settings?.settings.webhook_secret ?? "Not set"}
          value={form.webhook_secret ?? ""}
          onChange={(v) => setForm((f) => ({ ...f, webhook_secret: v }))}
        />

        <div className="flex items-center gap-2 pt-2">
          <Button
            onClick={handleSave}
            disabled={Object.keys(form).length === 0 || update.isPending}
            loading={update.isPending}
          >
            {update.isPending ? "Saving..." : "Save Changes"}
          </Button>
          <Button variant="outline" onClick={() => setTestOpen(true)}>
            <Send className="size-3.5 mr-1.5" /> Send Test WhatsApp
          </Button>
        </div>
      </div>

      <div className="bg-background border border-border p-6 space-y-3 h-fit">
        <h3 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
          Connection & Webhook
        </h3>
        <StatusPill status={health?.connection_status} />
        {health?.connection_detail && (
          <p className="text-xs text-muted-foreground">{health.connection_detail}</p>
        )}

        {health?.webhook_url && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">Webhook URL</p>
            <div className="flex items-center gap-1.5">
              <code className="text-[11px] break-all bg-secondary/60 rounded px-2 py-1 flex-1">
                {health.webhook_url}
              </code>
              <Button variant="ghost" size="icon" className="size-7" onClick={copyWebhookUrl}>
                <Copy className="size-3.5" />
              </Button>
            </div>
          </div>
        )}

        <dl className="text-xs space-y-1.5 pt-1">
          <Row
            label="Webhook Verification"
            value={health?.webhook_verification_configured ? "Configured" : "Not configured"}
          />
          <Row label="Last Webhook Received" value={formatDate(health?.last_webhook_at)} />
          <Row label="Last Successful Connection" value={formatDate(health?.last_success_at)} />
          <Row label="Last Failed Connection" value={formatDate(health?.last_failure_at)} />
        </dl>
      </div>

      <Dialog open={testOpen} onOpenChange={setTestOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send Test WhatsApp Message</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="+91XXXXXXXXXX"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
            />
            <Input
              placeholder="Approved Meta template name"
              value={testTemplate}
              onChange={(e) => setTestTemplate(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTestOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleTestSend}
              disabled={!testTo || !testTemplate || testWhatsApp.isPending}
              loading={testWhatsApp.isPending}
            >
              {testWhatsApp.isPending ? "Sending..." : "Send"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label className="text-xs text-muted-foreground mb-1 block">{label}</label>
      <Input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium text-right">{value}</dd>
    </div>
  );
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}
