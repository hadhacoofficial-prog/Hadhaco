import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { EmailProviderSettings } from "@/components/admin/notifications/EmailProviderSettings";
import { WhatsAppProviderSettings } from "@/components/admin/notifications/WhatsAppProviderSettings";

export const Route = createFileRoute("/admin/notifications/providers")({
  component: ProviderSettingsPage,
});

function ProviderSettingsPage() {
  const [tab, setTab] = useState<"email" | "whatsapp">("email");

  return (
    <div>
      <div className="flex gap-1 mb-6" role="tablist" aria-label="Provider">
        {(["email", "whatsapp"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm rounded-full transition-colors ${
              tab === t
                ? "bg-foreground text-background"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            {t === "email" ? "Email (Resend)" : "WhatsApp (Meta)"}
          </button>
        ))}
      </div>

      {tab === "email" ? <EmailProviderSettings /> : <WhatsAppProviderSettings />}
    </div>
  );
}
