import { useState, useEffect } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { toast } from "sonner";
import { Save, Settings2, Phone, Globe, MapPin, FileText } from "lucide-react";
import { useCompanyConfig, useUpdateCompanyConfig } from "@hadha/shared-api";
import { FormSkeleton } from "@/components/loading/FormSkeleton";
import type { CompanyConfigUpdate } from "@hadha/shared-types";

export const Route = createFileRoute("/admin/templates")({
  component: AdminTemplates,
});

function Field({
  label,
  name,
  value,
  onChange,
  placeholder,
  hint,
  type = "text",
  maxLength,
}: {
  label: string;
  name: string;
  value: string;
  onChange: (name: string, value: string) => void;
  placeholder?: string;
  hint?: string;
  type?: string;
  maxLength?: number;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(name, e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-foreground/20"
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-6 space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        {icon}
        <h2 className="text-base font-semibold">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function AdminTemplates() {
  const { data: config, isLoading } = useCompanyConfig();
  const update = useUpdateCompanyConfig();

  const [form, setForm] = useState<Record<keyof CompanyConfigUpdate, string>>({
    name: "",
    tagline: "",
    gstin: "",
    city: "",
    state: "",
    postal_code: "",
    country: "IN",
    phone: "",
    support_email: "",
    website: "",
    logo_url: "",
    packing_slip_logo_url: "",
    shipping_label_logo_url: "",
    instagram_url: "",
    facebook_url: "",
  });
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    // Guard with `!dirty` so a background refetch (query invalidation,
    // window refocus, etc.) can't silently clobber in-progress edits the
    // user hasn't saved yet.
    if (config && !dirty) {
      setForm({
        name: config.name ?? "",
        tagline: config.tagline ?? "",
        gstin: config.gstin ?? "",
        city: config.city ?? "",
        state: config.state ?? "",
        postal_code: config.postal_code ?? "",
        country: config.country ?? "IN",
        phone: config.phone ?? "",
        support_email: config.support_email ?? "",
        website: config.website ?? "",
        logo_url: config.logo_url ?? "",
        packing_slip_logo_url: config.packing_slip_logo_url ?? "",
        shipping_label_logo_url: config.shipping_label_logo_url ?? "",
        instagram_url: config.instagram_url ?? "",
        facebook_url: config.facebook_url ?? "",
      });
    }
  }, [config, dirty]);

  function handleChange(name: string, value: string) {
    // Country is a 2-letter ISO code (DB column is varchar(2)) — force
    // uppercase and truncate defensively so a stray full country name
    // can't reach the API and fail the whole save.
    const nextValue = name === "country" ? value.toUpperCase().slice(0, 2) : value;
    setForm((prev) => ({ ...prev, [name]: nextValue }));
    setDirty(true);
  }

  async function handleSave() {
    const payload = Object.fromEntries(
      Object.entries(form).map(([k, v]) => [k, v === "" ? null : v]),
    ) as CompanyConfigUpdate;
    try {
      await update.mutateAsync(payload);
      toast.success("Company settings saved");
      setDirty(false);
    } catch {
      toast.error("Failed to save settings");
    }
  }

  if (isLoading) {
    return (
      <div className="max-w-3xl space-y-6">
        <FormSkeleton fields={4} columns={2} showTitle />
        <FormSkeleton fields={4} columns={2} showTitle />
        <FormSkeleton fields={3} columns={2} showTitle />
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Template Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure company details used in packing slips, shipping labels, and emails.
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={!dirty || update.isPending}
          aria-busy={update.isPending}
          className="flex items-center gap-2 rounded-md bg-foreground text-background px-4 py-2 text-sm font-medium disabled:opacity-40 hover:opacity-90 transition"
        >
          <Save className="size-4" />
          {update.isPending ? "Saving…" : "Save Changes"}
        </button>
      </div>

      <Section title="Brand Identity" icon={<Settings2 className="size-4 text-muted-foreground" />}>
        <Field
          label="Company Name"
          name="name"
          value={form.name}
          onChange={handleChange}
          placeholder="Hadha Jewellery"
        />
        <Field
          label="Tagline"
          name="tagline"
          value={form.tagline}
          onChange={handleChange}
          placeholder="The strong Decision Â· à°¨à°¿à°°à±à°£à°¯à°‚ à°®à±€à°¦à°¿ à°¨à°¾à°£à±à°¯à°¤ à°®à°¾à°¦à°¿"
          hint="Shown below the logo on all documents."
        />
        <Field
          label="Logo URL"
          name="logo_url"
          value={form.logo_url}
          onChange={handleChange}
          placeholder="https://cdn.hadhajewellery.com/logo.png"
          hint="Upload via Media Manager and paste the public URL here."
        />
        <Field
          label="GSTIN"
          name="gstin"
          value={form.gstin}
          onChange={handleChange}
          placeholder="22AAAAA0000A1Z5"
        />
      </Section>

      <Section title="Address" icon={<MapPin className="size-4 text-muted-foreground" />}>
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="City"
            name="city"
            value={form.city}
            onChange={handleChange}
            placeholder="Hyderabad"
          />
          <Field
            label="State"
            name="state"
            value={form.state}
            onChange={handleChange}
            placeholder="Telangana"
          />
          <Field
            label="Postal Code"
            name="postal_code"
            value={form.postal_code}
            onChange={handleChange}
            placeholder="500033"
          />
          <Field
            label="Country Code"
            name="country"
            value={form.country}
            onChange={handleChange}
            placeholder="IN"
            maxLength={2}
            hint="2-letter ISO code only, e.g. IN — not the full country name."
          />
        </div>
      </Section>

      <Section title="Contact" icon={<Phone className="size-4 text-muted-foreground" />}>
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Phone"
            name="phone"
            value={form.phone}
            onChange={handleChange}
            placeholder="+91 98765 43210"
            type="tel"
          />
          <Field
            label="Support Email"
            name="support_email"
            value={form.support_email}
            onChange={handleChange}
            placeholder="info@hadhajewellery.com"
            type="email"
          />
          <Field
            label="Website"
            name="website"
            value={form.website}
            onChange={handleChange}
            placeholder="www.hadhajewellery.com"
          />
        </div>
      </Section>

      <Section title="Social Media" icon={<Globe className="size-4 text-muted-foreground" />}>
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Instagram URL"
            name="instagram_url"
            value={form.instagram_url}
            onChange={handleChange}
            placeholder="https://instagram.com/hadha"
          />
          <Field
            label="Facebook URL"
            name="facebook_url"
            value={form.facebook_url}
            onChange={handleChange}
            placeholder="https://facebook.com/hadha"
          />
        </div>
      </Section>

      <Section
        title="Document Branding"
        icon={<FileText className="size-4 text-muted-foreground" />}
      >
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Packing Slip Logo"
            name="packing_slip_logo_url"
            value={form.packing_slip_logo_url}
            onChange={handleChange}
            placeholder="https://cdn.hadhajewellery.com/packing-slip-logo.png"
            hint="Used only on Packing Slip PDFs. PNG with transparent background recommended."
          />
          <Field
            label="Shipping Label Logo"
            name="shipping_label_logo_url"
            value={form.shipping_label_logo_url}
            onChange={handleChange}
            placeholder="https://cdn.hadhajewellery.com/shipping-label-logo.png"
            hint="Used only on Shipping Label PDFs. PNG with transparent background recommended."
          />
        </div>
      </Section>

      <div className="rounded-lg border border-border bg-secondary/30 p-5 space-y-2">
        <div className="flex items-center gap-2">
          <FileText className="size-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Document Templates</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Packing slips and shipping labels are generated automatically from the company settings
          above. Email templates will be configurable here in a future update.
        </p>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <div className="rounded-md border border-border bg-card p-3">
            <div className="text-sm font-medium">Packing Slip</div>
            <div className="text-xs text-muted-foreground mt-1">
              A4, shows order items, addresses, and totals
            </div>
          </div>
          <div className="rounded-md border border-border bg-card p-3">
            <div className="text-sm font-medium">Shipping Label</div>
            <div className="text-xs text-muted-foreground mt-1">
              A4, shows delivery address for courier handlers
            </div>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={!dirty || update.isPending}
          aria-busy={update.isPending}
          className="flex items-center gap-2 rounded-md bg-foreground text-background px-5 py-2.5 text-sm font-medium disabled:opacity-40 hover:opacity-90 transition"
        >
          <Save className="size-4" />
          {update.isPending ? "Saving…" : "Save Changes"}
        </button>
      </div>
    </div>
  );
}
