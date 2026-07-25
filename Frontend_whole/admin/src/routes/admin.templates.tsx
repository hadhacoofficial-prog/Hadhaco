import { useState, useEffect } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { toast } from "sonner";
import {
  Save,
  Settings2,
  Phone,
  MapPin,
  FileText,
  Share2,
  Search,
  Palette,
  Building2,
} from "lucide-react";
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

function TextArea({
  label,
  name,
  value,
  onChange,
  placeholder,
  hint,
  rows = 3,
}: {
  label: string;
  name: string;
  value: string;
  onChange: (name: string, value: string) => void;
  placeholder?: string;
  hint?: string;
  rows?: number;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(name, e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-foreground/20 resize-none"
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

  const [form, setForm] = useState<Record<string, string>>({
    name: "",
    legal_name: "",
    brand_name: "",
    tagline: "",
    description: "",
    website: "",
    domain: "",
    logo_url: "",
    favicon_url: "",
    packing_slip_logo_url: "",
    shipping_label_logo_url: "",
    phone: "",
    alternate_phone: "",
    whatsapp: "",
    support_email: "",
    sales_email: "",
    address_line_1: "",
    address_line_2: "",
    city: "",
    state: "",
    postal_code: "",
    country: "IN",
    google_maps_url: "",
    gstin: "",
    cin: "",
    business_hours: "",
    instagram_url: "",
    facebook_url: "",
    youtube_url: "",
    twitter_x_url: "",
    linkedin_url: "",
    pinterest_url: "",
    default_meta_title: "",
    default_meta_description: "",
    organization_description: "",
    theme_color: "",
  });
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    // Guard with `!dirty` so a background refetch (query invalidation,
    // window refocus, etc.) can't silently clobber in-progress edits the
    // user hasn't saved yet.
    if (config && !dirty) {
      setForm({
        name: config.name ?? "",
        legal_name: config.legal_name ?? "",
        brand_name: config.brand_name ?? "",
        tagline: config.tagline ?? "",
        description: config.description ?? "",
        website: config.website ?? "",
        domain: config.domain ?? "",
        logo_url: config.logo_url ?? "",
        favicon_url: config.favicon_url ?? "",
        packing_slip_logo_url: config.packing_slip_logo_url ?? "",
        shipping_label_logo_url: config.shipping_label_logo_url ?? "",
        phone: config.phone ?? "",
        alternate_phone: config.alternate_phone ?? "",
        whatsapp: config.whatsapp ?? "",
        support_email: config.support_email ?? "",
        sales_email: config.sales_email ?? "",
        address_line_1: config.address_line_1 ?? "",
        address_line_2: config.address_line_2 ?? "",
        city: config.city ?? "",
        state: config.state ?? "",
        postal_code: config.postal_code ?? "",
        country: config.country ?? "IN",
        google_maps_url: config.google_maps_url ?? "",
        gstin: config.gstin ?? "",
        cin: config.cin ?? "",
        business_hours: config.business_hours ?? "",
        instagram_url: config.instagram_url ?? "",
        facebook_url: config.facebook_url ?? "",
        youtube_url: config.youtube_url ?? "",
        twitter_x_url: config.twitter_x_url ?? "",
        linkedin_url: config.linkedin_url ?? "",
        pinterest_url: config.pinterest_url ?? "",
        default_meta_title: config.default_meta_title ?? "",
        default_meta_description: config.default_meta_description ?? "",
        organization_description: config.organization_description ?? "",
        theme_color: config.theme_color ?? "",
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
          <h1 className="text-2xl font-bold">Company Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Single source of truth for all company information across the storefront, admin, and
            notifications.
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={!dirty || update.isPending}
          aria-busy={update.isPending}
          className="flex items-center gap-2 rounded-md bg-foreground text-background px-4 py-2 text-sm font-medium disabled:opacity-40 hover:opacity-90 transition"
        >
          <Save className="size-4" />
          {update.isPending ? "Saving\u2026" : "Save Changes"}
        </button>
      </div>

      {/* ── Brand Identity ─────────────────────────────────────────────── */}
      <Section title="Brand Identity" icon={<Settings2 className="size-4 text-muted-foreground" />}>
        <Field
          label="Company Name"
          name="name"
          value={form.name}
          onChange={handleChange}
          placeholder="Hadha Silver Jewellery"
          hint="Primary company name used in documents, emails, and the storefront."
        />
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Legal Name"
            name="legal_name"
            value={form.legal_name}
            onChange={handleChange}
            placeholder="Hadha Silver Jewellery Pvt. Ltd."
            hint="Full registered entity name for invoices and legal docs."
          />
          <Field
            label="Brand Name"
            name="brand_name"
            value={form.brand_name}
            onChange={handleChange}
            placeholder="Hadha"
            hint="Short consumer-facing brand name. Shown in footers, meta tags, etc."
          />
        </div>
        <Field
          label="Tagline"
          name="tagline"
          value={form.tagline}
          onChange={handleChange}
          placeholder="Handcrafted 92.5 Silver Jewellery"
          hint="Shown below the logo on documents and storefront."
        />
        <TextArea
          label="Company Description"
          name="description"
          value={form.description}
          onChange={handleChange}
          placeholder="Premium handcrafted 92.5 sterling silver jewellery..."
          hint="Used in the footer, about page, and meta descriptions."
          rows={3}
        />
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Website"
            name="website"
            value={form.website}
            onChange={handleChange}
            placeholder="https://hadha.co"
          />
          <Field
            label="Domain"
            name="domain"
            value={form.domain}
            onChange={handleChange}
            placeholder="hadha.co"
            hint="Bare domain for SEO previews and structured data."
          />
        </div>
      </Section>

      {/* ── Logos ──────────────────────────────────────────────────────── */}
      <Section title="Logos" icon={<FileText className="size-4 text-muted-foreground" />}>
        <Field
          label="Primary Logo URL"
          name="logo_url"
          value={form.logo_url}
          onChange={handleChange}
          placeholder="https://cdn.example.com/logo.png"
          hint="Used in storefront header, footer, packing slips, and emails."
        />
        <Field
          label="Favicon URL"
          name="favicon_url"
          value={form.favicon_url}
          onChange={handleChange}
          placeholder="https://cdn.example.com/favicon.png"
          hint="16x16 or 32x32 PNG for the browser tab icon."
        />
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Packing Slip Logo"
            name="packing_slip_logo_url"
            value={form.packing_slip_logo_url}
            onChange={handleChange}
            placeholder="https://cdn.example.com/packing-slip-logo.png"
            hint="Transparent PNG recommended."
          />
          <Field
            label="Shipping Label Logo"
            name="shipping_label_logo_url"
            value={form.shipping_label_logo_url}
            onChange={handleChange}
            placeholder="https://cdn.example.com/shipping-label-logo.png"
            hint="Transparent PNG recommended."
          />
        </div>
      </Section>

      {/* ── Contact ────────────────────────────────────────────────────── */}
      <Section title="Contact" icon={<Phone className="size-4 text-muted-foreground" />}>
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Phone"
            name="phone"
            value={form.phone}
            onChange={handleChange}
            placeholder="+91 90000 00000"
            type="tel"
          />
          <Field
            label="Alternate Phone"
            name="alternate_phone"
            value={form.alternate_phone}
            onChange={handleChange}
            placeholder="+91 90000 00001"
            type="tel"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="WhatsApp Number"
            name="whatsapp"
            value={form.whatsapp}
            onChange={handleChange}
            placeholder="+91 90000 00000"
            type="tel"
            hint="Digits only used for the wa.me link."
          />
          <Field
            label="Business Hours"
            name="business_hours"
            value={form.business_hours}
            onChange={handleChange}
            placeholder="Mon\u2013Sat, 10am\u20137pm"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Support Email"
            name="support_email"
            value={form.support_email}
            onChange={handleChange}
            placeholder="support@hadha.co"
            type="email"
          />
          <Field
            label="Sales Email"
            name="sales_email"
            value={form.sales_email}
            onChange={handleChange}
            placeholder="sales@hadha.co"
            type="email"
          />
        </div>
      </Section>

      {/* ── Address ────────────────────────────────────────────────────── */}
      <Section title="Address" icon={<MapPin className="size-4 text-muted-foreground" />}>
        <Field
          label="Address Line 1"
          name="address_line_1"
          value={form.address_line_1}
          onChange={handleChange}
          placeholder="MVP Sector 1, MVP Colony"
        />
        <Field
          label="Address Line 2"
          name="address_line_2"
          value={form.address_line_2}
          onChange={handleChange}
          placeholder="Landmark / Floor / Suite (optional)"
        />
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="City"
            name="city"
            value={form.city}
            onChange={handleChange}
            placeholder="Visakhapatnam"
          />
          <Field
            label="State"
            name="state"
            value={form.state}
            onChange={handleChange}
            placeholder="Andhra Pradesh"
          />
          <Field
            label="Postal Code"
            name="postal_code"
            value={form.postal_code}
            onChange={handleChange}
            placeholder="530017"
          />
          <Field
            label="Country Code"
            name="country"
            value={form.country}
            onChange={handleChange}
            placeholder="IN"
            maxLength={2}
            hint="2-letter ISO code only."
          />
        </div>
        <Field
          label="Google Maps URL"
          name="google_maps_url"
          value={form.google_maps_url}
          onChange={handleChange}
          placeholder="https://maps.app.goo.gl/..."
          hint="Share link from Google Maps."
        />
      </Section>

      {/* ── Business / Compliance ──────────────────────────────────────── */}
      <Section
        title="Business & Compliance"
        icon={<Building2 className="size-4 text-muted-foreground" />}
      >
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="GSTIN"
            name="gstin"
            value={form.gstin}
            onChange={handleChange}
            placeholder="22AAAAA0000A1Z5"
            hint="15-character GST registration number."
          />
          <Field
            label="CIN"
            name="cin"
            value={form.cin}
            onChange={handleChange}
            placeholder="U74999AP2017PTC123456"
            hint="Corporate Identification Number (if applicable)."
          />
        </div>
      </Section>

      {/* ── Social Media ───────────────────────────────────────────────── */}
      <Section title="Social Media" icon={<Share2 className="size-4 text-muted-foreground" />}>
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Instagram"
            name="instagram_url"
            value={form.instagram_url}
            onChange={handleChange}
            placeholder="https://instagram.com/..."
          />
          <Field
            label="Facebook"
            name="facebook_url"
            value={form.facebook_url}
            onChange={handleChange}
            placeholder="https://facebook.com/..."
          />
          <Field
            label="YouTube"
            name="youtube_url"
            value={form.youtube_url}
            onChange={handleChange}
            placeholder="https://youtube.com/@..."
          />
          <Field
            label="X (Twitter)"
            name="twitter_x_url"
            value={form.twitter_x_url}
            onChange={handleChange}
            placeholder="https://x.com/..."
          />
          <Field
            label="LinkedIn"
            name="linkedin_url"
            value={form.linkedin_url}
            onChange={handleChange}
            placeholder="https://linkedin.com/company/..."
          />
          <Field
            label="Pinterest"
            name="pinterest_url"
            value={form.pinterest_url}
            onChange={handleChange}
            placeholder="https://pinterest.com/..."
          />
        </div>
      </Section>

      {/* ── SEO & Meta ────────────────────────────────────────────────── */}
      <Section title="SEO & Meta" icon={<Search className="size-4 text-muted-foreground" />}>
        <Field
          label="Default Meta Title"
          name="default_meta_title"
          value={form.default_meta_title}
          onChange={handleChange}
          placeholder="Hadha | 92.5 Silver Jewellery"
          hint="Used when a page doesn\u2019t set its own title."
        />
        <TextArea
          label="Default Meta Description"
          name="default_meta_description"
          value={form.default_meta_description}
          onChange={handleChange}
          placeholder="Premium handcrafted 92.5 sterling silver jewellery..."
          hint="150\u2013160 characters recommended."
          rows={2}
        />
        <TextArea
          label="Organization Description"
          name="organization_description"
          value={form.organization_description}
          onChange={handleChange}
          placeholder="Hadha is a handcrafted sterling silver jewellery brand..."
          hint="Used in structured data (JSON-LD) for search engines."
          rows={3}
        />
      </Section>

      {/* ── Theme ──────────────────────────────────────────────────────── */}
      <Section title="Theme" icon={<Palette className="size-4 text-muted-foreground" />}>
        <div className="grid grid-cols-2 gap-4 items-end">
          <Field
            label="Theme Color"
            name="theme_color"
            value={form.theme_color}
            onChange={handleChange}
            placeholder="#A8C8E8"
            hint="Browser address bar color and og:theme_color."
          />
          {form.theme_color && (
            <div className="flex items-center gap-2 pb-1">
              <div
                className="size-8 rounded-md border border-border"
                style={{ backgroundColor: form.theme_color }}
              />
              <span className="text-xs text-muted-foreground">Preview</span>
            </div>
          )}
        </div>
      </Section>

      {/* ── Document Templates Info ────────────────────────────────────── */}
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
          {update.isPending ? "Saving\u2026" : "Save Changes"}
        </button>
      </div>
    </div>
  );
}
