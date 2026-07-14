import { useState } from "react";
import { toast } from "sonner";
import { Send } from "lucide-react";
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
  useTestEmailProvider,
  useUpdateProviderSettings,
} from "@/hooks/admin/useNotificationAdmin";

export function EmailProviderSettings() {
  const { data: settings, isLoading } = useProviderSettings("email");
  const { data: health } = useProviderHealth("email");
  const update = useUpdateProviderSettings("email");
  const testEmail = useTestEmailProvider();

  const [form, setForm] = useState<Record<string, string>>({});
  const [testOpen, setTestOpen] = useState(false);
  const [testTo, setTestTo] = useState("");

  const value = (key: string) => form[key] ?? settings?.settings[key] ?? "";

  const handleSave = () => {
    update.mutate(form, {
      onSuccess: () => {
        toast.success("Email settings updated");
        setForm({});
      },
      onError: (e) => toast.error(toUserMessage(e)),
    });
  };

  const handleTestSend = () => {
    testEmail.mutate(testTo, {
      onSuccess: (result) => {
        if (result.success) toast.success(result.message);
        else toast.error(result.message);
        setTestOpen(false);
      },
      onError: (e) => toast.error(toUserMessage(e)),
    });
  };

  if (isLoading) {
    return <FormSkeleton fields={5} columns={1} />;
  }

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 bg-background border border-border p-6 space-y-4">
        <div className="flex items-center justify-between">
          <Label htmlFor="email-enabled" className="text-sm">
            Enable Email Notifications
          </Label>
          <Switch
            id="email-enabled"
            checked={value("enabled") !== "false"}
            onCheckedChange={(checked) => setForm((f) => ({ ...f, enabled: String(checked) }))}
          />
        </div>

        <Field
          label="Sender Name"
          value={value("from_name")}
          onChange={(v) => setForm((f) => ({ ...f, from_name: v }))}
        />
        <Field
          label="Sender Email"
          value={value("from_email")}
          onChange={(v) => setForm((f) => ({ ...f, from_email: v }))}
        />
        <Field
          label="Reply-To"
          value={value("reply_to")}
          onChange={(v) => setForm((f) => ({ ...f, reply_to: v }))}
        />
        <Field
          label="API Key"
          placeholder={settings?.settings.api_key ?? "Not set"}
          value={form.api_key ?? ""}
          onChange={(v) => setForm((f) => ({ ...f, api_key: v }))}
          type="password"
        />

        <div className="flex items-center gap-2 pt-2">
          <Button
            onClick={handleSave}
            disabled={Object.keys(form).length === 0 || update.isPending}
          >
            Save Changes
          </Button>
          <Button variant="outline" onClick={() => setTestOpen(true)}>
            <Send className="size-3.5 mr-1.5" /> Send Test Email
          </Button>
        </div>
      </div>

      <div className="bg-background border border-border p-6 space-y-3 h-fit">
        <h3 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
          Connection Status
        </h3>
        <StatusPill status={health?.connection_status} />
        {health?.connection_detail && (
          <p className="text-xs text-muted-foreground">{health.connection_detail}</p>
        )}
        <dl className="text-xs space-y-1.5 pt-2">
          <Row label="Last Successful Connection" value={formatDate(health?.last_success_at)} />
          <Row label="Last Failed Connection" value={formatDate(health?.last_failure_at)} />
        </dl>
      </div>

      <Dialog open={testOpen} onOpenChange={setTestOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send Test Email</DialogTitle>
          </DialogHeader>
          <Input
            placeholder="recipient@example.com"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setTestOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleTestSend} disabled={!testTo || testEmail.isPending}>
              Send
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

export function StatusPill({ status }: { status: string | undefined }) {
  const map: Record<string, string> = {
    connected: "bg-emerald-50 text-emerald-700",
    error: "bg-red-50 text-red-700",
    not_configured: "bg-secondary text-muted-foreground",
  };
  const label: Record<string, string> = {
    connected: "Connected",
    error: "Error",
    not_configured: "Not configured",
  };
  return (
    <span
      className={`inline-block text-xs px-2.5 py-1 rounded-full ${
        status ? (map[status] ?? "bg-secondary") : "bg-secondary"
      }`}
    >
      {status ? (label[status] ?? status) : "Unknown"}
    </span>
  );
}
