import { memo, useCallback, useEffect, useRef, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowDownToLine,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Eye,
  EyeOff,
  ExternalLink,
  FileText,
  Film,
  GripVertical,
  ImageIcon,
  Instagram,
  LayoutGrid,
  Layers,
  Mail,
  Megaphone,
  Navigation,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  ShoppingBag,
  Star,
  Trash2,
  X,
  Zap,
} from "lucide-react";

import {
  useCmsSections,
  useReorderSections,
  useToggleSection,
  useInvalidateCache,
} from "@/hooks/cms/useCmsSections";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { ImageUploadField } from "@/components/cms/ImageUploadField";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";

import { AnnouncementBar } from "@/components/site/AnnouncementBar";
import { Hero } from "@/components/site/Hero";
import { Newsletter } from "@/components/site/Newsletter";
import { PromoBanner } from "@/components/site/PromoBanner";
import { CraftsmanshipVideo } from "@/components/site/CraftsmanshipVideo";
import { InstagramSection } from "@/components/site/InstagramSection";
import { FeaturedProducts } from "@/components/site/FeaturedProducts";
import { WhyChooseUs } from "@/components/site/WhyChooseUs";
import { Reviews } from "@/components/site/Reviews";
import { FeaturedCollection } from "@/components/site/FeaturedCollection";
import { Footer } from "@/components/site/Footer";

import type {
  AdminSection,
  AnnouncementConfig,
  AnnouncementItemConfig,
  CollectionCardConfig,
  FooterConfig,
  HeroCarouselConfig,
  HeroSlideConfig,
  ImageBannerConfig,
  InstagramGalleryConfig,
  InstagramItemConfig,
  NewsletterConfig,
  ProductGridConfig,
  ReviewItemConfig,
  SectionItem,
  SectionType,
  VideoSectionConfig,
  WhyChooseCardConfig,
} from "@/types/cms";
import type { ProductListItem, ProductListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/cms/")({
  component: AdminCmsEditor,
});

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const PREVIEW_W = 1280;

const NATURAL_H: Partial<Record<SectionType, number>> = {
  announcement_bar: 44,
  navbar: 72,
  hero_carousel: 600,
  image_banner: 440,
  video_section: 600,
  newsletter: 360,
  instagram_gallery: 480,
  footer: 420,
  category_grid: 360,
  collection_showcase: 400,
  product_grid: 460,
  testimonials: 360,
  content_block: 460,
  custom: 280,
};

const SECTION_ICONS: Record<string, React.ReactElement> = {
  announcement_bar: <Megaphone className="size-3.5" />,
  hero_carousel: <ImageIcon className="size-3.5" />,
  navbar: <Navigation className="size-3.5" />,
  category_grid: <LayoutGrid className="size-3.5" />,
  collection_showcase: <Layers className="size-3.5" />,
  product_grid: <ShoppingBag className="size-3.5" />,
  video_section: <Film className="size-3.5" />,
  image_banner: <ImageIcon className="size-3.5" />,
  content_block: <FileText className="size-3.5" />,
  testimonials: <Star className="size-3.5" />,
  instagram_gallery: <Instagram className="size-3.5" />,
  newsletter: <Mail className="size-3.5" />,
  footer: <ArrowDownToLine className="size-3.5" />,
  custom: <Settings className="size-3.5" />,
};

const TYPE_LABELS: Record<string, string> = {
  announcement_bar: "Announcement Bar",
  hero_carousel: "Hero Carousel",
  navbar: "Navbar",
  category_grid: "Category Grid",
  collection_showcase: "Collection Showcase",
  product_grid: "Product Grid",
  video_section: "Video Section",
  image_banner: "Image Banner",
  content_block: "Content Block",
  testimonials: "Testimonials",
  instagram_gallery: "Instagram Gallery",
  newsletter: "Newsletter",
  footer: "Footer",
  custom: "Custom",
};

const STATUS_CLS: Record<string, string> = {
  published: "bg-emerald-50 text-emerald-700 border-emerald-200",
  draft: "bg-amber-50 text-amber-700 border-amber-200",
  scheduled: "bg-sky-50 text-sky-700 border-sky-200",
};

const DEFAULT_CONFIGS: Partial<Record<SectionType, Record<string, unknown>>> = {
  announcement_bar: { rotation_speed: 4, show_close: true },
  hero_carousel: { auto_rotate: true, rotation_speed: 6 },
  image_banner: {
    title: "The Hadha Edit",
    subtitle: "Timeless sterling silver jewellery",
    overlay: true,
    overlay_opacity: 0.5,
    cta_text: "Shop the edit",
    cta_url: "/collections",
  },
  newsletter: {
    heading: "Be first to know.",
    description: "Early access to new collections, exclusive offers, and style notes.",
    placeholder: "Your email address",
    btn_text: "Subscribe",
    success_message: "Thank you for subscribing.",
  },
  video_section: {
    eyebrow: "Our Craft",
    title: "Made by hand. Worn with heart.",
    subtitle: "Every piece is crafted in Visakhapatnam by skilled artisans.",
    autoplay: true,
    loop: true,
    muted: true,
    controls: false,
    cta_text: "Our story",
    cta_url: "/about",
  },
  instagram_gallery: {
    title: "Worn by our community.",
    handle: "hadha.silver",
    max_items: 6,
    source: "manual",
  },
  product_grid: {
    title: "Most-loved silver, curated.",
    eyebrow: "Featured",
    source: "featured",
    max_products: 8,
    view_all_url: "/search",
  },
  footer: {
    copyright_name: "Hadha Silver",
    company_address: "Visakhapatnam, Andhra Pradesh, India",
    phone: "+91 9000000000",
    email: "hello@hadha.co",
    description: "Handcrafted 92.5 sterling silver jewellery from Visakhapatnam.",
  },
};

const DEFAULT_ITEMS: Partial<Record<SectionType, Array<Record<string, unknown>>>> = {
  announcement_bar: [
    { text: "FREE SHIPPING ABOVE ₹999", bg_color: "#0F2340", text_color: "#FFFFFF" },
    { text: "Certified 92.5 Sterling Silver", bg_color: "#0F2340", text_color: "#FFFFFF" },
    { text: "Handcrafted in Visakhapatnam", bg_color: "#0F2340", text_color: "#FFFFFF" },
  ],
  collection_showcase: [
    {
      image_url: "",
      eyebrow: "Featured edit",
      title: "Finger Rings, redefined.",
      subtitle:
        "Stylish rings crafted to bring subtle elegance to every look — from stackable everyday bands to statement temple stones.",
      button_text: "Shop rings",
      button_url: "/collections",
    },
    {
      image_url: "",
      eyebrow: "Bestseller",
      title: "The Bugadi edit.",
      subtitle:
        "Heritage temple ear cuffs reimagined — non-piercing, press-on, and poised to become your new favourite.",
      button_text: "Discover Bugadi",
      button_url: "/collections",
    },
  ],
  content_block: [
    {
      icon: "shield",
      title: "92.5 Sterling Silver",
      text: "BIS-hallmarked. Guaranteed purity in every piece we craft.",
    },
    {
      icon: "gem",
      title: "Authentic Craftsmanship",
      text: "Hand-finished by master silversmiths in our Visakhapatnam atelier.",
    },
    {
      icon: "sparkles",
      title: "Trusted Quality",
      text: "Anti-tarnish coating and lifetime polish on every Hadha creation.",
    },
    {
      icon: "heart",
      title: "Made With Love",
      text: "A family heirloom in the making — gift-wrapped and delivered with care.",
    },
  ],
  testimonials: [
    {
      customer_name: "Priya S.",
      text: "The sterling silver anklet I ordered arrived beautifully packaged. The craftsmanship is exquisite — I've received so many compliments.",
      rating: 5,
    },
    {
      customer_name: "Ananya R.",
      text: "I've been buying jewellery for years and Hadha's quality is truly outstanding. My oxidised silver necklace is stunning.",
      rating: 5,
    },
    {
      customer_name: "Meera K.",
      text: "Fast shipping, gorgeous packaging, and the ring fits perfectly. Will definitely be ordering again for Diwali gifts.",
      rating: 5,
    },
    {
      customer_name: "Divya T.",
      text: "Hadha has become my go-to for silver jewellery. The BIS hallmark gives me complete confidence in the quality.",
      rating: 5,
    },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Form primitives
// ─────────────────────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground mb-1.5">
        {label}
      </p>
      {children}
    </div>
  );
}

const inputCls =
  "w-full border border-border/60 bg-background/80 px-3 py-2 text-sm outline-none focus:border-primary transition-colors rounded-sm placeholder:text-muted-foreground/50";
const inputSmCls =
  "w-full border border-border/60 bg-background/80 px-2.5 py-1.5 text-xs outline-none focus:border-primary transition-colors rounded-sm placeholder:text-muted-foreground/40";

function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={inputCls}
    />
  );
}

function TextInputSm({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={inputSmCls}
    />
  );
}

function TextArea({
  value,
  onChange,
  rows = 3,
}: {
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      rows={rows}
      onChange={(e) => onChange(e.target.value)}
      className={`${inputCls} resize-none`}
    />
  );
}

function ColorInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        value={value || "#000000"}
        onChange={(e) => onChange(e.target.value)}
        className="size-8 rounded cursor-pointer border border-border/60 bg-transparent p-0.5"
      />
      <TextInput value={value} onChange={onChange} placeholder="#000000" />
    </div>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-sm text-foreground/80">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 rounded-full transition-colors ${checked ? "bg-primary" : "bg-muted-foreground/30"}`}
      >
        <span
          className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-4" : "translate-x-0"}`}
        />
      </button>
    </div>
  );
}

function SliderRow({
  label,
  value,
  onChange,
  min = 1,
  max = 20,
  unit = "",
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  unit?: string;
}) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          {label}
        </p>
        <span className="text-xs font-mono text-foreground/50">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(+e.target.value)}
        className="w-full h-1 accent-primary"
      />
    </div>
  );
}

function SelectRow({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground mb-1.5">
        {label}
      </p>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={inputCls}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SectionSubheader({ label }: { label: string }) {
  return (
    <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground border-t border-border/40 pt-4">
      {label}
    </p>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Editors
// ─────────────────────────────────────────────────────────────────────────────

type EP<T> = { config: T; onChange: (next: T) => void };
type ItemCtrl = {
  items: SectionItem[];
  onItemChange: (items: SectionItem[]) => void;
  onAddItem: (cfg: Record<string, unknown>) => void;
  onDeleteItem: (id: string) => void;
  onDuplicateItem: (id: string) => void;
};

// ── Announcement Bar ──────────────────────────────────────────────────────────

function AnnouncementEditor({
  config,
  onChange,
  items,
  onItemChange,
}: EP<Partial<AnnouncementConfig>> & Pick<ItemCtrl, "items" | "onItemChange">) {
  function updateItem(idx: number, field: string, val: unknown) {
    onItemChange(
      items.map((it, i) => (i === idx ? { ...it, config: { ...it.config, [field]: val } } : it)),
    );
  }
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Messages
          </p>
          <Link
            to="/admin/cms/$sectionKey"
            params={{ sectionKey: "announcement_bar" }}
            className="text-[10px] text-primary hover:underline"
          >
            Manage all →
          </Link>
        </div>
        <div className="space-y-3">
          {items.map((item, i) => {
            const ic = item.config as unknown as AnnouncementItemConfig;
            return (
              <div
                key={item.id ?? i}
                className="p-3 border border-border/40 rounded-lg bg-muted/20 space-y-2"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`size-1.5 rounded-full flex-none ${item.is_enabled ? "bg-emerald-400" : "bg-muted-foreground/30"}`}
                  />
                  <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
                    Message {i + 1}
                  </span>
                </div>
                <Field label="Text">
                  <TextInput
                    value={ic.text ?? ""}
                    onChange={(v) => updateItem(i, "text", v)}
                    placeholder="FREE SHIPPING ABOVE ₹999"
                  />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Background">
                    <ColorInput
                      value={ic.bg_color ?? "#0F2340"}
                      onChange={(v) => updateItem(i, "bg_color", v)}
                    />
                  </Field>
                  <Field label="Text color">
                    <ColorInput
                      value={ic.text_color ?? "#FFFFFF"}
                      onChange={(v) => updateItem(i, "text_color", v)}
                    />
                  </Field>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <SectionSubheader label="Display settings" />
      <SliderRow
        label="Rotation speed"
        value={config.rotation_speed ?? 4}
        min={1}
        max={20}
        unit="s"
        onChange={(v) => onChange({ ...config, rotation_speed: v })}
      />
      <ToggleRow
        label="Show close button"
        checked={config.show_close ?? true}
        onChange={(v) => onChange({ ...config, show_close: v })}
      />
    </div>
  );
}

// ── Hero Carousel ─────────────────────────────────────────────────────────────

function HeroSlideCard({
  item,
  index,
  expanded,
  onToggleExpand,
  onUpdate,
  onDelete,
  onDuplicate,
  onToggleEnabled,
}: {
  item: SectionItem;
  index: number;
  expanded: boolean;
  onToggleExpand: () => void;
  onUpdate: (field: keyof HeroSlideConfig, val: unknown) => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onToggleEnabled: () => void;
}) {
  const slide = item.config as unknown as HeroSlideConfig;
  return (
    <div
      className={`border rounded-xl overflow-hidden transition-all ${item.is_enabled ? "border-border/50" : "border-border/20 opacity-50"}`}
    >
      {/* Card header */}
      <div className="flex items-center gap-2 p-3 bg-muted/20">
        <GripVertical className="size-4 text-muted-foreground/30 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium truncate">
            Slide {index + 1}
            {slide.eyebrow ? ` — ${slide.eyebrow}` : ""}
          </p>
          <p className="text-[10px] text-muted-foreground truncate">
            {slide.headline || "Untitled slide"}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onToggleEnabled}
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title={item.is_enabled ? "Hide" : "Show"}
          >
            {item.is_enabled ? (
              <Eye className="size-3.5 text-muted-foreground" />
            ) : (
              <EyeOff className="size-3.5 text-muted-foreground" />
            )}
          </button>
          <button
            onClick={onDuplicate}
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Duplicate"
          >
            <Copy className="size-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded hover:bg-red-50 hover:text-red-500 transition-colors"
            title="Delete"
          >
            <Trash2 className="size-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={onToggleExpand}
            className="p-1.5 rounded hover:bg-muted transition-colors"
          >
            {expanded ? (
              <ChevronUp className="size-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="size-3.5 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>
      {/* Expanded fields */}
      {expanded && (
        <div className="p-4 space-y-4 border-t border-border/30">
          <ImageUploadField
            label="Desktop image"
            value={slide.desktop_image_url ?? ""}
            onChange={(v) => onUpdate("desktop_image_url", v)}
            folder="/cms/hero"
            previewHeight={90}
          />
          <ImageUploadField
            label="Mobile image"
            value={slide.mobile_image_url ?? ""}
            onChange={(v) => onUpdate("mobile_image_url", v)}
            folder="/cms/hero"
            previewHeight={70}
          />
          <ImageUploadField
            label="Tablet image"
            value={slide.tablet_image_url ?? ""}
            onChange={(v) => onUpdate("tablet_image_url", v)}
            folder="/cms/hero"
            previewHeight={70}
          />
          <Field label="Eyebrow tag">
            <TextInput
              value={slide.eyebrow ?? ""}
              onChange={(v) => onUpdate("eyebrow", v)}
              placeholder="FEATURED GIFTING"
            />
          </Field>
          <Field label="Headline">
            <TextArea
              value={slide.headline ?? ""}
              onChange={(v) => onUpdate("headline", v)}
              rows={2}
            />
          </Field>
          <Field label="Description">
            <TextArea
              value={slide.subheading ?? ""}
              onChange={(v) => onUpdate("subheading", v)}
              rows={2}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Primary button text">
              <TextInput
                value={slide.primary_btn_text ?? ""}
                onChange={(v) => onUpdate("primary_btn_text", v)}
                placeholder="OUR STORY"
              />
            </Field>
            <Field label="Primary button URL">
              <TextInput
                value={slide.primary_btn_url ?? ""}
                onChange={(v) => onUpdate("primary_btn_url", v)}
                placeholder="/about"
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Secondary button text">
              <TextInput
                value={slide.secondary_btn_text ?? ""}
                onChange={(v) => onUpdate("secondary_btn_text", v)}
                placeholder="EXPLORE GIFTING"
              />
            </Field>
            <Field label="Secondary button URL">
              <TextInput
                value={slide.secondary_btn_url ?? ""}
                onChange={(v) => onUpdate("secondary_btn_url", v)}
                placeholder="/collections"
              />
            </Field>
          </div>
          <SelectRow
            label="Text alignment"
            value={slide.alignment ?? "left"}
            onChange={(v) => onUpdate("alignment", v)}
            options={[
              { value: "left", label: "Left" },
              { value: "center", label: "Center" },
              { value: "right", label: "Right" },
            ]}
          />
          <ToggleRow
            label="Overlay"
            checked={slide.overlay ?? true}
            onChange={(v) => onUpdate("overlay", v)}
          />
          {(slide.overlay ?? true) && (
            <SliderRow
              label="Overlay opacity"
              value={Math.round((slide.overlay_opacity ?? 0.5) * 100)}
              min={0}
              max={100}
              unit="%"
              onChange={(v) => onUpdate("overlay_opacity", v / 100)}
            />
          )}
          <Field label="SEO alt text">
            <TextInput
              value={slide.seo_alt ?? ""}
              onChange={(v) => onUpdate("seo_alt", v)}
              placeholder="Hero image description"
            />
          </Field>
        </div>
      )}
    </div>
  );
}

function HeroEditor({
  config,
  onChange,
  items,
  onItemChange,
  onAddItem,
  onDeleteItem,
  onDuplicateItem,
}: EP<Partial<HeroCarouselConfig>> & ItemCtrl) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function updateSlide(idx: number, field: keyof HeroSlideConfig, val: unknown) {
    onItemChange(
      items.map((it, i) => (i === idx ? { ...it, config: { ...it.config, [field]: val } } : it)),
    );
  }

  function toggleEnabled(idx: number) {
    onItemChange(items.map((it, i) => (i === idx ? { ...it, is_enabled: !it.is_enabled } : it)));
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Slides ({items.length})
          </p>
          <button
            onClick={() => {
              const newId = `__new_${Date.now()}`;
              onAddItem({
                desktop_image_url: "",
                headline: "New Slide",
                eyebrow: "",
                subheading: "",
                primary_btn_text: "Shop Now",
                primary_btn_url: "/collections",
                overlay: true,
                overlay_opacity: 0.5,
                alignment: "left",
              });
              setTimeout(() => setExpandedIds((prev) => new Set(prev).add(newId)), 50);
            }}
            className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-primary hover:text-primary/80 transition-colors"
          >
            <Plus className="size-3.5" /> Add Slide
          </button>
        </div>
        {items.length === 0 ? (
          <p className="text-xs text-muted-foreground italic py-4 text-center">
            No slides yet. Click "Add Slide" to get started.
          </p>
        ) : (
          <div className="space-y-2.5">
            {items.map((item, i) => (
              <HeroSlideCard
                key={item.id}
                item={item}
                index={i}
                expanded={expandedIds.has(item.id)}
                onToggleExpand={() => toggleExpand(item.id)}
                onUpdate={(field, val) => updateSlide(i, field, val)}
                onDelete={() => onDeleteItem(item.id)}
                onDuplicate={() => onDuplicateItem(item.id)}
                onToggleEnabled={() => toggleEnabled(i)}
              />
            ))}
          </div>
        )}
      </div>
      <SectionSubheader label="Carousel settings" />
      <ToggleRow
        label="Auto rotate"
        checked={config.auto_rotate ?? true}
        onChange={(v) => onChange({ ...config, auto_rotate: v })}
      />
      <SliderRow
        label="Rotation speed"
        value={config.rotation_speed ?? 6}
        min={2}
        max={30}
        unit="s"
        onChange={(v) => onChange({ ...config, rotation_speed: v })}
      />
    </div>
  );
}

// ── Image Banner ──────────────────────────────────────────────────────────────

function ImageBannerEditor({ config, onChange }: EP<Partial<ImageBannerConfig>>) {
  const up = (k: keyof ImageBannerConfig, v: unknown) => onChange({ ...config, [k]: v });
  return (
    <div className="space-y-5">
      <ImageUploadField
        label="Desktop image"
        value={config.desktop_image_url ?? ""}
        onChange={(v) => up("desktop_image_url", v)}
        folder="/cms/banners"
        previewHeight={100}
      />
      <ImageUploadField
        label="Mobile image"
        value={config.mobile_image_url ?? ""}
        onChange={(v) => up("mobile_image_url", v)}
        folder="/cms/banners"
        previewHeight={80}
      />
      <Field label="Title">
        <TextInput
          value={config.title ?? ""}
          onChange={(v) => up("title", v)}
          placeholder="The Bugadi Edit"
        />
      </Field>
      <Field label="Subtitle">
        <TextInput value={config.subtitle ?? ""} onChange={(v) => up("subtitle", v)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="CTA text">
          <TextInput
            value={config.cta_text ?? ""}
            onChange={(v) => up("cta_text", v)}
            placeholder="Shop the edit"
          />
        </Field>
        <Field label="CTA URL">
          <TextInput
            value={config.cta_url ?? ""}
            onChange={(v) => up("cta_url", v)}
            placeholder="/collections"
          />
        </Field>
      </div>
      <ToggleRow
        label="Overlay"
        checked={config.overlay ?? true}
        onChange={(v) => up("overlay", v)}
      />
      {(config.overlay ?? true) && (
        <SliderRow
          label="Overlay opacity"
          value={Math.round((config.overlay_opacity ?? 0.5) * 100)}
          min={0}
          max={100}
          unit="%"
          onChange={(v) => up("overlay_opacity", v / 100)}
        />
      )}
    </div>
  );
}

// ── Newsletter ────────────────────────────────────────────────────────────────

function NewsletterEditor({ config, onChange }: EP<Partial<NewsletterConfig>>) {
  const up = (k: keyof NewsletterConfig, v: string) => onChange({ ...config, [k]: v });
  return (
    <div className="space-y-5">
      <Field label="Heading">
        <TextInput
          value={config.heading ?? ""}
          onChange={(v) => up("heading", v)}
          placeholder="Be first to know."
        />
      </Field>
      <Field label="Description">
        <TextArea value={config.description ?? ""} onChange={(v) => up("description", v)} />
      </Field>
      <Field label="Input placeholder">
        <TextInput
          value={config.placeholder ?? ""}
          onChange={(v) => up("placeholder", v)}
          placeholder="Your email address"
        />
      </Field>
      <Field label="Button text">
        <TextInput
          value={config.btn_text ?? ""}
          onChange={(v) => up("btn_text", v)}
          placeholder="Subscribe"
        />
      </Field>
      <Field label="Success message">
        <TextInput
          value={config.success_message ?? ""}
          onChange={(v) => up("success_message", v)}
        />
      </Field>
      <Field label="Background color">
        <ColorInput value={config.bg_color ?? ""} onChange={(v) => up("bg_color", v)} />
      </Field>
    </div>
  );
}

// ── Video ─────────────────────────────────────────────────────────────────────

function VideoEditor({ config, onChange }: EP<Partial<VideoSectionConfig>>) {
  const up = (k: keyof VideoSectionConfig, v: unknown) => onChange({ ...config, [k]: v });
  return (
    <div className="space-y-5">
      <Field label="Eyebrow">
        <TextInput
          value={config.eyebrow ?? ""}
          onChange={(v) => up("eyebrow", v)}
          placeholder="Our Craft"
        />
      </Field>
      <Field label="Title">
        <TextInput
          value={config.title ?? ""}
          onChange={(v) => up("title", v)}
          placeholder="Made by hand. Worn with heart."
        />
      </Field>
      <Field label="Subtitle">
        <TextArea value={config.subtitle ?? ""} onChange={(v) => up("subtitle", v)} rows={2} />
      </Field>
      <ImageUploadField
        label="Video file (MP4)"
        value={config.mp4_url ?? ""}
        onChange={(v) => up("mp4_url", v)}
        accept="video/mp4,video/*"
        folder="/cms/video"
        previewHeight={0}
      />
      <ImageUploadField
        label="Poster image"
        value={config.poster_url ?? ""}
        onChange={(v) => up("poster_url", v)}
        folder="/cms/video"
        previewHeight={80}
      />
      <div className="grid grid-cols-2 gap-3">
        <Field label="CTA text">
          <TextInput
            value={config.cta_text ?? ""}
            onChange={(v) => up("cta_text", v)}
            placeholder="Our Story"
          />
        </Field>
        <Field label="CTA URL">
          <TextInput
            value={config.cta_url ?? ""}
            onChange={(v) => up("cta_url", v)}
            placeholder="/about"
          />
        </Field>
      </div>
      <SectionSubheader label="Playback" />
      <div className="grid grid-cols-2 gap-3">
        {(["autoplay", "loop", "muted", "controls"] as const).map((k) => (
          <ToggleRow
            key={k}
            label={k.charAt(0).toUpperCase() + k.slice(1)}
            checked={config[k] ?? k !== "controls"}
            onChange={(v) => up(k, v)}
          />
        ))}
      </div>
    </div>
  );
}

// ── Instagram Gallery (items-based) ──────────────────────────────────────────

function InstagramItemCard({
  item,
  index,
  onUpdate,
  onDelete,
  onDuplicate,
  onToggleEnabled,
}: {
  item: SectionItem;
  index: number;
  onUpdate: (field: keyof InstagramItemConfig, val: string) => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onToggleEnabled: () => void;
}) {
  const ic = item.config as unknown as InstagramItemConfig;
  return (
    <div
      className={`border border-border/40 rounded-xl overflow-hidden ${!item.is_enabled ? "opacity-50" : ""}`}
    >
      {ic.image_url && (
        <div className="relative">
          <ImageWithFallback src={ic.image_url} alt="" className="w-full h-28" />
        </div>
      )}
      <div className="p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground font-medium">Tile {index + 1}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={onToggleEnabled}
              className="p-1 rounded hover:bg-muted transition-colors"
            >
              {item.is_enabled ? (
                <Eye className="size-3 text-muted-foreground" />
              ) : (
                <EyeOff className="size-3 text-muted-foreground" />
              )}
            </button>
            <button onClick={onDuplicate} className="p-1 rounded hover:bg-muted transition-colors">
              <Copy className="size-3 text-muted-foreground" />
            </button>
            <button
              onClick={onDelete}
              className="p-1 rounded hover:bg-red-50 hover:text-red-500 transition-colors"
            >
              <Trash2 className="size-3 text-muted-foreground" />
            </button>
          </div>
        </div>
        <ImageUploadField
          value={ic.image_url ?? ""}
          onChange={(v) => onUpdate("image_url", v)}
          folder="/cms/instagram"
          previewHeight={0}
        />
        <div className="space-y-1.5">
          <TextInputSm
            value={ic.link_url ?? ""}
            onChange={(v) => onUpdate("link_url", v)}
            placeholder="Redirect URL (optional)"
          />
          <TextInputSm
            value={ic.alt_text ?? ""}
            onChange={(v) => onUpdate("alt_text", v)}
            placeholder="Alt text"
          />
        </div>
      </div>
    </div>
  );
}

function InstagramEditor({
  config,
  onChange,
  items,
  onItemChange,
  onAddItem,
  onDeleteItem,
  onDuplicateItem,
}: EP<Partial<InstagramGalleryConfig>> & ItemCtrl) {
  function updateItem(idx: number, field: keyof InstagramItemConfig, val: string) {
    onItemChange(
      items.map((it, i) => (i === idx ? { ...it, config: { ...it.config, [field]: val } } : it)),
    );
  }
  function toggleEnabled(idx: number) {
    onItemChange(items.map((it, i) => (i === idx ? { ...it, is_enabled: !it.is_enabled } : it)));
  }
  return (
    <div className="space-y-5">
      <Field label="Section title">
        <TextInput
          value={config.title ?? ""}
          onChange={(v) => onChange({ ...config, title: v })}
          placeholder="Worn by our community."
        />
      </Field>
      <Field label="Instagram handle">
        <TextInput
          value={config.handle ?? ""}
          onChange={(v) => onChange({ ...config, handle: v })}
          placeholder="hadha.silver"
        />
      </Field>
      <SelectRow
        label="Image source"
        value={config.source ?? "manual"}
        onChange={(v) => onChange({ ...config, source: v as InstagramGalleryConfig["source"] })}
        options={[
          { value: "manual", label: "Manual (uploaded images)" },
          { value: "collections", label: "From collections" },
        ]}
      />
      <SliderRow
        label="Max images"
        value={config.max_items ?? 6}
        min={3}
        max={12}
        onChange={(v) => onChange({ ...config, max_items: v })}
      />

      {(config.source ?? "manual") === "manual" && (
        <div>
          <SectionSubheader label={`Gallery images (${items.length})`} />
          <div className="mt-3 mb-2 flex justify-end">
            <button
              onClick={() => onAddItem({ image_url: "", link_url: "", alt_text: "" })}
              className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-primary hover:text-primary/80 transition-colors"
            >
              <Plus className="size-3.5" /> Add Image
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {items.map((item, i) => (
              <InstagramItemCard
                key={item.id}
                item={item}
                index={i}
                onUpdate={(field, val) => updateItem(i, field, val)}
                onDelete={() => onDeleteItem(item.id)}
                onDuplicate={() => onDuplicateItem(item.id)}
                onToggleEnabled={() => toggleEnabled(i)}
              />
            ))}
          </div>
          {items.length === 0 && (
            <p className="text-xs text-muted-foreground italic text-center py-4">
              No images yet. Click "Add Image" to start.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Product Grid (Featured / New Arrivals / Trending) ─────────────────────────

function ProductPickerEditor({ config, onChange }: EP<Partial<ProductGridConfig>>) {
  const [search, setSearch] = useState("");
  const source = config.source ?? "featured";
  const selectedIds = new Set(config.manual_product_ids ?? []);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.products.list({ page_size: 100 }),
    queryFn: () => api.get<ProductListResponse>("/products", { params: { page_size: 100 } }),
    staleTime: 5 * 60_000,
    enabled: source === "manual",
  });

  const allProducts = data?.items ?? [];
  const filtered = allProducts.filter(
    (p) =>
      !search ||
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.sku.toLowerCase().includes(search.toLowerCase()),
  );

  function toggleProduct(id: string) {
    const current = new Set(config.manual_product_ids ?? []);
    if (current.has(id)) current.delete(id);
    else current.add(id);
    onChange({ ...config, manual_product_ids: Array.from(current) });
  }

  return (
    <div className="space-y-5">
      <Field label="Section title">
        <TextInput
          value={config.title ?? ""}
          onChange={(v) => onChange({ ...config, title: v })}
          placeholder="Most-loved silver, curated."
        />
      </Field>
      <Field label="Eyebrow">
        <TextInput
          value={config.eyebrow ?? ""}
          onChange={(v) => onChange({ ...config, eyebrow: v })}
          placeholder="Featured products"
        />
      </Field>
      <SelectRow
        label="Product source"
        value={source}
        onChange={(v) => onChange({ ...config, source: v as ProductGridConfig["source"] })}
        options={[
          { value: "featured", label: "Featured (is_featured=true)" },
          { value: "newest", label: "New Arrivals" },
          { value: "best_seller", label: "Best Sellers" },
          { value: "trending", label: "Trending" },
          { value: "manual", label: "Manual Selection" },
        ]}
      />
      <SliderRow
        label="Max products"
        value={config.max_products ?? 8}
        min={2}
        max={24}
        onChange={(v) => onChange({ ...config, max_products: v })}
      />
      <Field label="View all URL">
        <TextInput
          value={config.view_all_url ?? ""}
          onChange={(v) => onChange({ ...config, view_all_url: v })}
          placeholder="/search"
        />
      </Field>

      {source === "manual" && (
        <div>
          <SectionSubheader label={`Manual selection (${selectedIds.size} selected)`} />
          <div className="mt-3 relative mb-2">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or SKU…"
              className="w-full border border-border/60 bg-background/80 pl-8 pr-3 py-2 text-sm outline-none focus:border-primary transition-colors rounded-sm"
            />
          </div>
          <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
            {isLoading && (
              <div className="space-y-1.5">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 rounded-lg" />
                ))}
              </div>
            )}
            {filtered.map((p: ProductListItem) => {
              const selected = selectedIds.has(p.id);
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => toggleProduct(p.id)}
                  className={`w-full flex items-center gap-3 p-2 rounded-lg border transition-colors text-left ${selected ? "border-primary/50 bg-primary/5" : "border-border/40 hover:border-border hover:bg-muted/30"}`}
                >
                  <div className="size-10 rounded overflow-hidden shrink-0 bg-muted">
                    {p.primary_image && (
                      <ImageWithFallback src={p.primary_image} alt="" className="size-full" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{p.name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {p.sku} · ₹{p.base_price}
                    </p>
                  </div>
                  <div
                    className={`size-4 rounded border-2 shrink-0 flex items-center justify-center transition-colors ${selected ? "border-primary bg-primary" : "border-border/60"}`}
                  >
                    {selected && <Check className="size-2.5 text-primary-foreground" />}
                  </div>
                </button>
              );
            })}
            {!isLoading && filtered.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-4">No products found.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Collection Cards ──────────────────────────────────────────────────────────

function CollectionCardItem({
  item,
  index,
  onUpdate,
  onDelete,
  onDuplicate,
  onToggleEnabled,
}: {
  item: SectionItem;
  index: number;
  onUpdate: (field: keyof CollectionCardConfig, val: unknown) => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onToggleEnabled: () => void;
}) {
  const [open, setOpen] = useState(false);
  const c = item.config as unknown as CollectionCardConfig;
  return (
    <div
      className={`border border-border/40 rounded-xl overflow-hidden ${!item.is_enabled ? "opacity-50" : ""}`}
    >
      <div className="flex items-center gap-2 p-3 bg-muted/20">
        <GripVertical className="size-4 text-muted-foreground/30 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium truncate">
            Card {index + 1}
            {c.title ? ` — ${c.title}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onToggleEnabled}
            className="p-1.5 rounded hover:bg-muted transition-colors"
          >
            {item.is_enabled ? (
              <Eye className="size-3.5 text-muted-foreground" />
            ) : (
              <EyeOff className="size-3.5 text-muted-foreground" />
            )}
          </button>
          <button onClick={onDuplicate} className="p-1.5 rounded hover:bg-muted transition-colors">
            <Copy className="size-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded hover:bg-red-50 hover:text-red-500 transition-colors"
          >
            <Trash2 className="size-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={() => setOpen((v) => !v)}
            className="p-1.5 rounded hover:bg-muted transition-colors"
          >
            {open ? (
              <ChevronUp className="size-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="size-3.5 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>
      {open && (
        <div className="p-4 space-y-4 border-t border-border/30">
          <ImageUploadField
            label="Card image"
            value={c.image_url ?? ""}
            onChange={(v) => onUpdate("image_url", v)}
            folder="/cms/collections"
            previewHeight={90}
          />
          <ImageUploadField
            label="Hover image"
            value={c.hover_image_url ?? ""}
            onChange={(v) => onUpdate("hover_image_url", v)}
            folder="/cms/collections"
            previewHeight={70}
          />
          <Field label="Eyebrow tag">
            <TextInput
              value={c.eyebrow ?? ""}
              onChange={(v) => onUpdate("eyebrow", v)}
              placeholder="Featured edit"
            />
          </Field>
          <Field label="Title">
            <TextInput
              value={c.title ?? ""}
              onChange={(v) => onUpdate("title", v)}
              placeholder="Nakshi Mala"
            />
          </Field>
          <Field label="Subtitle">
            <TextArea value={c.subtitle ?? ""} onChange={(v) => onUpdate("subtitle", v)} rows={2} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Button text">
              <TextInput
                value={c.button_text ?? ""}
                onChange={(v) => onUpdate("button_text", v)}
                placeholder="Shop now"
              />
            </Field>
            <Field label="Button URL">
              <TextInput
                value={c.button_url ?? ""}
                onChange={(v) => onUpdate("button_url", v)}
                placeholder="/collections/nakshi"
              />
            </Field>
          </div>
        </div>
      )}
    </div>
  );
}

function CollectionCardsEditor({
  items,
  onItemChange,
  onAddItem,
  onDeleteItem,
  onDuplicateItem,
}: ItemCtrl & { config: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  function updateItem(idx: number, field: keyof CollectionCardConfig, val: unknown) {
    onItemChange(
      items.map((it, i) => (i === idx ? { ...it, config: { ...it.config, [field]: val } } : it)),
    );
  }
  function toggleEnabled(idx: number) {
    onItemChange(items.map((it, i) => (i === idx ? { ...it, is_enabled: !it.is_enabled } : it)));
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Collection cards ({items.length})
        </p>
        <button
          onClick={() =>
            onAddItem({
              image_url: "",
              eyebrow: "",
              title: "",
              subtitle: "",
              button_text: "Shop now",
              button_url: "/collections",
            })
          }
          className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-primary hover:text-primary/80 transition-colors"
        >
          <Plus className="size-3.5" /> Add Card
        </button>
      </div>
      <div className="space-y-2.5">
        {items.map((item, i) => (
          <CollectionCardItem
            key={item.id}
            item={item}
            index={i}
            onUpdate={(field, val) => updateItem(i, field, val)}
            onDelete={() => onDeleteItem(item.id)}
            onDuplicate={() => onDuplicateItem(item.id)}
            onToggleEnabled={() => toggleEnabled(i)}
          />
        ))}
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground italic text-center py-4">
            No cards yet. Click "Add Card".
          </p>
        )}
      </div>
    </div>
  );
}

// ── Why Choose Hadha ──────────────────────────────────────────────────────────

const WHY_CHOOSE_ICON_OPTIONS = [
  { value: "shield", label: "Shield" },
  { value: "gem", label: "Gem" },
  { value: "sparkles", label: "Sparkles" },
  { value: "heart", label: "Heart" },
];

function WhyChooseCardItem({
  item,
  index,
  onUpdate,
  onDelete,
  onDuplicate,
}: {
  item: SectionItem;
  index: number;
  onUpdate: (field: keyof WhyChooseCardConfig, val: string) => void;
  onDelete: () => void;
  onDuplicate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const c = item.config as unknown as WhyChooseCardConfig;
  return (
    <div className="border border-border/40 rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 p-3 bg-muted/20">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium truncate">{c.title || `Card ${index + 1}`}</p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onDuplicate} className="p-1.5 rounded hover:bg-muted transition-colors">
            <Copy className="size-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded hover:bg-red-50 hover:text-red-500 transition-colors"
          >
            <Trash2 className="size-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={() => setOpen((v) => !v)}
            className="p-1.5 rounded hover:bg-muted transition-colors"
          >
            {open ? (
              <ChevronUp className="size-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="size-3.5 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>
      {open && (
        <div className="p-4 space-y-4 border-t border-border/30">
          <SelectRow
            label="Icon"
            value={c.icon ?? "shield"}
            onChange={(v) => onUpdate("icon", v)}
            options={WHY_CHOOSE_ICON_OPTIONS}
          />
          <Field label="Title">
            <TextInput
              value={c.title ?? ""}
              onChange={(v) => onUpdate("title", v)}
              placeholder="92.5 Sterling Silver"
            />
          </Field>
          <Field label="Text">
            <TextArea value={c.text ?? ""} onChange={(v) => onUpdate("text", v)} rows={3} />
          </Field>
        </div>
      )}
    </div>
  );
}

function WhyChooseEditor({
  items,
  onItemChange,
  onAddItem,
  onDeleteItem,
  onDuplicateItem,
}: ItemCtrl & { config: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  function updateItem(idx: number, field: keyof WhyChooseCardConfig, val: string) {
    onItemChange(
      items.map((it, i) => (i === idx ? { ...it, config: { ...it.config, [field]: val } } : it)),
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Cards ({items.length})
        </p>
        <button
          onClick={() => onAddItem({ icon: "shield", title: "", text: "" })}
          className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-primary hover:text-primary/80 transition-colors"
        >
          <Plus className="size-3.5" /> Add Card
        </button>
      </div>
      <div className="space-y-2.5">
        {items.map((item, i) => (
          <WhyChooseCardItem
            key={item.id}
            item={item}
            index={i}
            onUpdate={(field, val) => updateItem(i, field, val)}
            onDelete={() => onDeleteItem(item.id)}
            onDuplicate={() => onDuplicateItem(item.id)}
          />
        ))}
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground italic text-center py-4">
            No cards yet. Click "Add Card".
          </p>
        )}
      </div>
    </div>
  );
}

// ── Customer Reviews ──────────────────────────────────────────────────────────

function ReviewItemCard({
  item,
  index,
  onUpdate,
  onDelete,
  onDuplicate,
}: {
  item: SectionItem;
  index: number;
  onUpdate: (field: keyof ReviewItemConfig, val: unknown) => void;
  onDelete: () => void;
  onDuplicate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const r = item.config as unknown as ReviewItemConfig;
  return (
    <div className="border border-border/40 rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 p-3 bg-muted/20">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium truncate">{r.customer_name || `Review ${index + 1}`}</p>
          <div className="flex">
            {Array.from({ length: 5 }).map((_, i) => (
              <Star
                key={i}
                className={`size-3 ${i < (r.rating ?? 5) ? "text-amber-400 fill-amber-400" : "text-muted-foreground/20"}`}
              />
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onDuplicate} className="p-1.5 rounded hover:bg-muted transition-colors">
            <Copy className="size-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded hover:bg-red-50 hover:text-red-500 transition-colors"
          >
            <Trash2 className="size-3.5 text-muted-foreground" />
          </button>
          <button
            onClick={() => setOpen((v) => !v)}
            className="p-1.5 rounded hover:bg-muted transition-colors"
          >
            {open ? (
              <ChevronUp className="size-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="size-3.5 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>
      {open && (
        <div className="p-4 space-y-4 border-t border-border/30">
          <ImageUploadField
            label="Customer photo"
            value={r.photo_url ?? ""}
            onChange={(v) => onUpdate("photo_url", v)}
            folder="/cms/reviews"
            previewHeight={60}
          />
          <Field label="Customer name">
            <TextInput
              value={r.customer_name ?? ""}
              onChange={(v) => onUpdate("customer_name", v)}
              placeholder="Ananya P."
            />
          </Field>
          <Field label="Location">
            <TextInput
              value={r.location ?? ""}
              onChange={(v) => onUpdate("location", v)}
              placeholder="Visakhapatnam"
            />
          </Field>
          <SliderRow
            label="Rating"
            value={r.rating ?? 5}
            min={1}
            max={5}
            onChange={(v) => onUpdate("rating", v)}
          />
          <Field label="Review text">
            <TextArea value={r.text ?? ""} onChange={(v) => onUpdate("text", v)} rows={3} />
          </Field>
          <ToggleRow
            label="Verified purchase"
            checked={r.verified ?? false}
            onChange={(v) => onUpdate("verified", v)}
          />
        </div>
      )}
    </div>
  );
}

function ReviewsEditor({
  items,
  onItemChange,
  onAddItem,
  onDeleteItem,
  onDuplicateItem,
}: ItemCtrl & { config: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  function updateItem(idx: number, field: keyof ReviewItemConfig, val: unknown) {
    onItemChange(
      items.map((it, i) => (i === idx ? { ...it, config: { ...it.config, [field]: val } } : it)),
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Reviews ({items.length})
        </p>
        <button
          onClick={() => onAddItem({ customer_name: "", rating: 5, text: "", verified: true })}
          className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-primary hover:text-primary/80 transition-colors"
        >
          <Plus className="size-3.5" /> Add Review
        </button>
      </div>
      <div className="space-y-2.5">
        {items.map((item, i) => (
          <ReviewItemCard
            key={item.id}
            item={item}
            index={i}
            onUpdate={(field, val) => updateItem(i, field, val)}
            onDelete={() => onDeleteItem(item.id)}
            onDuplicate={() => onDuplicateItem(item.id)}
          />
        ))}
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground italic text-center py-4">
            No reviews yet. Click "Add Review".
          </p>
        )}
      </div>
    </div>
  );
}

// ── Footer ────────────────────────────────────────────────────────────────────

function FooterEditor({ config, onChange }: EP<Partial<FooterConfig>>) {
  const up = (k: keyof FooterConfig) => (v: unknown) => onChange({ ...config, [k]: v });
  const cols = (config.columns ?? []) as FooterConfig["columns"];

  function updateColumn(colIdx: number, field: "title" | "links", val: unknown) {
    const next = (cols ?? []).map((c, i) => (i === colIdx ? { ...c, [field]: val } : c));
    onChange({ ...config, columns: next });
  }
  function addLink(colIdx: number) {
    const next = (cols ?? []).map((c, i) =>
      i === colIdx ? { ...c, links: [...c.links, { label: "New link", url: "/" }] } : c,
    );
    onChange({ ...config, columns: next });
  }
  function updateLink(colIdx: number, linkIdx: number, field: "label" | "url", val: string) {
    const next = (cols ?? []).map((c, i) =>
      i === colIdx
        ? { ...c, links: c.links.map((l, j) => (j === linkIdx ? { ...l, [field]: val } : l)) }
        : c,
    );
    onChange({ ...config, columns: next });
  }
  function deleteLink(colIdx: number, linkIdx: number) {
    const next = (cols ?? []).map((c, i) =>
      i === colIdx ? { ...c, links: c.links.filter((_, j) => j !== linkIdx) } : c,
    );
    onChange({ ...config, columns: next });
  }
  function addColumn() {
    onChange({ ...config, columns: [...(cols ?? []), { title: "New column", links: [] }] });
  }
  function deleteColumn(colIdx: number) {
    onChange({ ...config, columns: (cols ?? []).filter((_, i) => i !== colIdx) });
  }

  return (
    <div className="space-y-5">
      <ImageUploadField
        label="Logo"
        value={config.logo_url ?? ""}
        onChange={up("logo_url") as (v: string) => void}
        folder="/cms/footer"
        previewHeight={60}
      />
      <Field label="Company name">
        <TextInput
          value={config.copyright_name ?? ""}
          onChange={up("copyright_name") as (v: string) => void}
          placeholder="Hadha Silver"
        />
      </Field>
      <Field label="Tagline">
        <TextArea
          value={config.description ?? ""}
          onChange={up("description") as (v: string) => void}
          rows={2}
        />
      </Field>
      <Field label="Address">
        <TextInput
          value={config.company_address ?? ""}
          onChange={up("company_address") as (v: string) => void}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Phone">
          <TextInput value={config.phone ?? ""} onChange={up("phone") as (v: string) => void} />
        </Field>
        <Field label="Email">
          <TextInput
            value={config.email ?? ""}
            onChange={up("email") as (v: string) => void}
            type="email"
          />
        </Field>
      </div>
      <SectionSubheader label="Social links" />
      <Field label="Instagram">
        <TextInput
          value={config.instagram ?? ""}
          onChange={up("instagram") as (v: string) => void}
          placeholder="https://instagram.com/hadha.silver"
        />
      </Field>
      <Field label="YouTube">
        <TextInput
          value={config.youtube ?? ""}
          onChange={up("youtube") as (v: string) => void}
          placeholder="https://youtube.com/..."
        />
      </Field>
      <Field label="WhatsApp">
        <TextInput
          value={config.whatsapp ?? ""}
          onChange={up("whatsapp") as (v: string) => void}
          placeholder="https://wa.me/91..."
        />
      </Field>

      <SectionSubheader label="Footer columns" />
      <div className="space-y-4 mt-3">
        {(cols ?? []).map((col, colIdx) => (
          <div key={colIdx} className="border border-border/40 rounded-xl p-3 space-y-3">
            <div className="flex items-center gap-2">
              <TextInputSm
                value={col.title}
                onChange={(v) => updateColumn(colIdx, "title", v)}
                placeholder="Column title"
              />
              <button
                onClick={() => deleteColumn(colIdx)}
                className="p-1.5 rounded hover:bg-red-50 hover:text-red-500 transition-colors shrink-0"
              >
                <Trash2 className="size-3.5 text-muted-foreground" />
              </button>
            </div>
            <div className="space-y-1.5 pl-2 border-l border-border/30">
              {col.links.map((link, linkIdx) => (
                <div key={linkIdx} className="flex items-center gap-1.5">
                  <TextInputSm
                    value={link.label}
                    onChange={(v) => updateLink(colIdx, linkIdx, "label", v)}
                    placeholder="Label"
                  />
                  <TextInputSm
                    value={link.url}
                    onChange={(v) => updateLink(colIdx, linkIdx, "url", v)}
                    placeholder="/path"
                  />
                  <button
                    onClick={() => deleteLink(colIdx, linkIdx)}
                    className="p-1 rounded hover:bg-red-50 hover:text-red-500 transition-colors shrink-0"
                  >
                    <X className="size-3 text-muted-foreground" />
                  </button>
                </div>
              ))}
              <button
                onClick={() => addLink(colIdx)}
                className="text-[10px] text-primary hover:underline flex items-center gap-1 mt-1"
              >
                <Plus className="size-3" /> Add link
              </button>
            </div>
          </div>
        ))}
        <button
          onClick={addColumn}
          className="w-full py-2 border border-dashed border-border/50 rounded-lg text-xs text-muted-foreground hover:border-primary hover:text-primary transition-colors"
        >
          + Add column
        </button>
      </div>
    </div>
  );
}

// ── Generic JSON editor ───────────────────────────────────────────────────────

function GenericEditor({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const [raw, setRaw] = useState(() => JSON.stringify(config, null, 2));
  const [err, setErr] = useState(false);
  useEffect(() => {
    setRaw(JSON.stringify(config, null, 2));
  }, [config]);
  function handle(s: string) {
    setRaw(s);
    try {
      onChange(JSON.parse(s));
      setErr(false);
    } catch {
      setErr(true);
    }
  }
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
        Raw config (JSON)
      </p>
      <textarea
        value={raw}
        rows={14}
        onChange={(e) => handle(e.target.value)}
        className={`w-full font-mono text-xs border ${err ? "border-destructive" : "border-border/60"} bg-muted/20 px-3 py-2 outline-none focus:border-primary transition-colors resize-none rounded-sm`}
      />
      {err && <p className="text-[11px] text-destructive mt-1">Invalid JSON</p>}
    </div>
  );
}

// ── Router ────────────────────────────────────────────────────────────────────

function SectionConfigEditor({
  section,
  config,
  onChange,
  items,
  onItemChange,
  onAddItem,
  onDeleteItem,
  onDuplicateItem,
}: {
  section: AdminSection;
  config: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  items: SectionItem[];
  onItemChange: (items: SectionItem[]) => void;
  onAddItem: (cfg: Record<string, unknown>) => void;
  onDeleteItem: (id: string) => void;
  onDuplicateItem: (id: string) => void;
}) {
  const ctrl: ItemCtrl = { items, onItemChange, onAddItem, onDeleteItem, onDuplicateItem };
  switch (section.section_type) {
    case "announcement_bar":
      return (
        <AnnouncementEditor
          config={config as unknown as Partial<AnnouncementConfig>}
          onChange={onChange as unknown as (next: Partial<AnnouncementConfig>) => void}
          items={items}
          onItemChange={onItemChange}
        />
      );
    case "hero_carousel":
      return (
        <HeroEditor
          config={config as unknown as Partial<HeroCarouselConfig>}
          onChange={onChange as unknown as (next: Partial<HeroCarouselConfig>) => void}
          {...ctrl}
        />
      );
    case "image_banner":
      return (
        <ImageBannerEditor
          config={config as unknown as Partial<ImageBannerConfig>}
          onChange={onChange as unknown as (next: Partial<ImageBannerConfig>) => void}
        />
      );
    case "newsletter":
      return (
        <NewsletterEditor
          config={config as unknown as Partial<NewsletterConfig>}
          onChange={onChange as unknown as (next: Partial<NewsletterConfig>) => void}
        />
      );
    case "video_section":
      return (
        <VideoEditor
          config={config as unknown as Partial<VideoSectionConfig>}
          onChange={onChange as unknown as (next: Partial<VideoSectionConfig>) => void}
        />
      );
    case "instagram_gallery":
      return (
        <InstagramEditor
          config={config as unknown as Partial<InstagramGalleryConfig>}
          onChange={onChange as unknown as (next: Partial<InstagramGalleryConfig>) => void}
          {...ctrl}
        />
      );
    case "product_grid":
      return (
        <ProductPickerEditor
          config={config as unknown as Partial<ProductGridConfig>}
          onChange={onChange as unknown as (next: Partial<ProductGridConfig>) => void}
        />
      );
    case "collection_showcase":
    case "category_grid":
      return <CollectionCardsEditor config={config} onChange={onChange} {...ctrl} />;
    case "testimonials":
      return <ReviewsEditor config={config} onChange={onChange} {...ctrl} />;
    case "content_block":
      return <WhyChooseEditor config={config} onChange={onChange} {...ctrl} />;
    case "footer":
      return (
        <FooterEditor
          config={config as unknown as Partial<FooterConfig>}
          onChange={onChange as unknown as (next: Partial<FooterConfig>) => void}
        />
      );
    default:
      return <GenericEditor config={config} onChange={onChange} />;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Preview utilities
// ─────────────────────────────────────────────────────────────────────────────

function usePreviewScale(ref: React.RefObject<HTMLDivElement | null>) {
  const [scale, setScale] = useState(0.6);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setScale(el.offsetWidth / PREVIEW_W);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return scale;
}

function renderSection(
  section: AdminSection,
  config: Record<string, unknown>,
  items: SectionItem[],
) {
  const naturalH = NATURAL_H[section.section_type as SectionType] ?? 300;
  switch (section.section_type) {
    case "announcement_bar":
      return <AnnouncementBar config={config as unknown as AnnouncementConfig} items={items} />;
    case "hero_carousel":
      return <Hero config={config as unknown as HeroCarouselConfig} items={items} />;
    case "image_banner":
      return <PromoBanner config={config as unknown as ImageBannerConfig} />;
    case "newsletter":
      return <Newsletter config={config as unknown as NewsletterConfig} />;
    case "video_section":
      return <CraftsmanshipVideo config={config as unknown as VideoSectionConfig} />;
    case "instagram_gallery":
      return (
        <InstagramSection config={config as unknown as InstagramGalleryConfig} items={items} />
      );
    case "product_grid":
      return <FeaturedProducts config={config as unknown as ProductGridConfig} />;
    case "content_block":
      return <WhyChooseUs items={items} />;
    case "testimonials":
      return <Reviews items={items} />;
    case "collection_showcase":
      return <FeaturedCollection items={items} />;
    case "footer":
      return <Footer config={config as unknown as FooterConfig} />;
    default:
      return (
        <div className="flex items-center justify-center bg-muted/20" style={{ height: naturalH }}>
          <div className="text-center">
            <div className="flex justify-center mb-2 text-muted-foreground/40">
              {SECTION_ICONS[section.section_type] ?? <Settings className="size-5" />}
            </div>
            <p className="text-sm font-medium text-foreground/50">
              {section.title ?? section.section_key}
            </p>
            <p className="text-xs text-muted-foreground">
              {TYPE_LABELS[section.section_type] ?? section.section_type}
            </p>
          </div>
        </div>
      );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Section card (left panel — Col 1)
// ─────────────────────────────────────────────────────────────────────────────

const SectionCard = memo(function SectionCard({
  section,
  idx,
  isActive,
  isDragging,
  isOver,
  onSelect,
  onToggle,
  onDragStart,
  onDragOver,
  onDrop,
  isDirty,
  onDuplicate,
  onDelete,
}: {
  section: AdminSection;
  idx: number;
  isActive: boolean;
  isDragging: boolean;
  isOver: boolean;
  onSelect: (key: string) => void;
  onToggle: (section: AdminSection) => void;
  isDirty: boolean;
  onDragStart: (idx: number) => void;
  onDragOver: (idx: number, e: React.DragEvent) => void;
  onDrop: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const chip = STATUS_CLS[section.status] ?? STATUS_CLS.published;
  return (
    <div
      draggable
      onDragStart={() => onDragStart(idx)}
      onDragOver={(e) => onDragOver(idx, e)}
      onDrop={onDrop}
      onDragEnd={onDrop}
      className={`relative rounded-xl border transition-all select-none ${
        isActive
          ? "border-primary/50 bg-primary/5 shadow-sm ring-1 ring-primary/20"
          : isOver
            ? "border-primary/40 bg-primary/5"
            : "border-border/60 bg-card hover:border-border hover:shadow-sm"
      } ${!section.is_active ? "opacity-40" : ""} ${isDragging ? "opacity-20 scale-95" : ""}`}
    >
      {isDirty && (
        <span
          className="absolute top-2.5 right-2.5 size-2 rounded-full bg-amber-400 shadow-sm z-10"
          title="Unsaved changes"
        />
      )}

      {/* Main row — clickable to select */}
      <button
        type="button"
        onClick={() => onSelect(section.section_key)}
        className="w-full flex items-center gap-2.5 p-3 cursor-pointer text-left"
      >
        <GripVertical className="size-4 text-muted-foreground/30 shrink-0 cursor-grab active:cursor-grabbing" />
        <div className="p-1.5 rounded-lg bg-muted text-muted-foreground shrink-0">
          {SECTION_ICONS[section.section_type] ?? <Settings className="size-3.5" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate leading-tight">
            {section.title ?? section.section_key}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span
              className={`text-[9px] px-1.5 py-0.5 rounded-full border font-medium leading-none ${chip}`}
            >
              {section.status}
            </span>
            <p className="text-[10px] text-muted-foreground truncate">
              {TYPE_LABELS[section.section_type]}
            </p>
          </div>
        </div>
        {isActive && <div className="size-1.5 rounded-full bg-primary shrink-0" />}
      </button>

      {/* Action bar */}
      <div className="flex items-center justify-between border-t border-border/30 px-3 py-1.5">
        <div className="flex items-center gap-0.5">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggle(section);
            }}
            className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title={section.is_active ? "Hide section" : "Show section"}
          >
            {section.is_active ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDuplicate();
            }}
            className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Duplicate section"
          >
            <Copy className="size-3.5" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="p-1.5 rounded-md hover:bg-red-50 hover:text-red-500 transition-colors text-muted-foreground"
            title="Delete section"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
        <button
          onClick={() => onSelect(section.section_key)}
          className={`px-2.5 py-1 rounded-md text-[10px] font-semibold uppercase tracking-wide transition-colors ${
            isActive
              ? "bg-primary text-primary-foreground"
              : "bg-muted hover:bg-primary/10 hover:text-primary text-muted-foreground"
          }`}
        >
          {isActive ? "Editing" : "Edit"}
        </button>
      </div>
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// Editor panel (Col 2 — form controls only, no preview)
// ─────────────────────────────────────────────────────────────────────────────

function SectionEditorPanel({
  section,
  config,
  onChange,
  items,
  onItemChange,
  onAddItem,
  onDeleteItem,
  onDuplicateItem,
  onSaveDraft,
  onPublish,
  onClose,
  isSaving,
  isPublishing,
  isDirty,
}: {
  section: AdminSection;
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
  items: SectionItem[];
  onItemChange: (items: SectionItem[]) => void;
  onAddItem: (cfg: Record<string, unknown>) => void;
  onDeleteItem: (id: string) => void;
  onDuplicateItem: (id: string) => void;
  onSaveDraft: () => void;
  onPublish: () => void;
  onClose: () => void;
  isSaving: boolean;
  isPublishing: boolean;
  isDirty: boolean;
}) {
  const chip = STATUS_CLS[section.status] ?? STATUS_CLS.published;
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-none px-4 py-3 border-b border-border/40 bg-background flex items-center gap-2.5">
        <button
          onClick={onClose}
          className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground shrink-0"
          title="Deselect section"
        >
          <X className="size-4" />
        </button>
        <div className="p-1.5 rounded-md bg-muted text-muted-foreground shrink-0">
          {SECTION_ICONS[section.section_type] ?? <Settings className="size-3.5" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold leading-tight truncate">
            {section.title ?? section.section_key}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span
              className={`text-[9px] px-1.5 py-0.5 rounded-full border font-medium leading-none ${chip}`}
            >
              {section.status}
            </span>
            <p className="text-[10px] text-muted-foreground truncate">
              {TYPE_LABELS[section.section_type]}
            </p>
          </div>
        </div>
        <Link
          to="/admin/cms/$sectionKey"
          params={{ sectionKey: section.section_key }}
          className="shrink-0 p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-primary"
          title="Advanced settings"
        >
          <ExternalLink className="size-3.5" />
        </Link>
      </div>

      {/* Scrollable editor — form controls only */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-5 space-y-5">
          <SectionConfigEditor
            section={section}
            config={config}
            onChange={onChange}
            items={items}
            onItemChange={onItemChange}
            onAddItem={onAddItem}
            onDeleteItem={onDeleteItem}
            onDuplicateItem={onDuplicateItem}
          />
        </div>
      </div>

      {/* Save / Publish footer */}
      <div className="flex-none border-t border-border/40 px-4 py-3 flex items-center justify-between bg-background/95 backdrop-blur-sm">
        {isDirty ? (
          <span className="text-xs text-amber-600 flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-amber-400 inline-block" /> Unsaved changes
          </span>
        ) : (
          <span className="text-xs text-muted-foreground/60">Saved</span>
        )}
        <div className="flex items-center gap-2">
          <button
            onClick={onSaveDraft}
            disabled={isSaving || !isDirty}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs border border-border rounded-lg hover:bg-muted disabled:opacity-40 transition-colors"
          >
            <Save className="size-3.5" />
            {isSaving ? "Saving…" : "Save Draft"}
          </button>
          <button
            onClick={onPublish}
            disabled={isPublishing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-60 transition-colors"
          >
            <Zap className="size-3.5" />
            {isPublishing ? "Publishing…" : "Publish"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Preview panel (Col 3 — live render, no controls)
// ─────────────────────────────────────────────────────────────────────────────

function PreviewPanel({
  section,
  config,
  items,
  isDirty,
}: {
  section: AdminSection;
  config: Record<string, unknown>;
  items: SectionItem[];
  isDirty: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scale = usePreviewScale(containerRef);
  const naturalH = NATURAL_H[section.section_type as SectionType] ?? 300;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Preview header */}
      <div className="flex-none px-4 py-2.5 border-b border-border/40 bg-background/70 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={`size-2 rounded-full inline-block ${isDirty ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`}
          />
          <p className="text-xs font-medium text-foreground/60">Live Preview</p>
          {isDirty && (
            <span className="text-[10px] text-amber-600 border border-amber-200 bg-amber-50 px-1.5 py-0.5 rounded-full">
              unsaved changes visible
            </span>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground truncate max-w-[200px]">
          {section.title ?? section.section_key}
        </p>
      </div>

      {/* Preview area — white background, scrollable */}
      <div className="flex-1 overflow-y-auto bg-white">
        <div ref={containerRef} className="w-full">
          <div
            className="relative overflow-hidden"
            style={{ height: Math.round(naturalH * scale) }}
          >
            <div
              className="pointer-events-none select-none absolute top-0 left-0"
              style={{
                width: PREVIEW_W,
                transform: `scale(${scale})`,
                transformOrigin: "top left",
              }}
            >
              {renderSection(section, config, items)}
            </div>
          </div>
        </div>
      </div>

      {/* Preview footer note */}
      <div className="flex-none px-4 py-2 border-t border-border/30 bg-background/50">
        <p className="text-[10px] text-muted-foreground/50 text-center">
          Preview updates instantly · {PREVIEW_W}px desktop viewport
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Editor empty state (Col 2 when nothing selected)
// ─────────────────────────────────────────────────────────────────────────────

function EditorEmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-8 py-16 gap-5">
      <div className="size-16 rounded-2xl bg-muted/60 flex items-center justify-center">
        <Layers className="size-7 text-muted-foreground/40" />
      </div>
      <div>
        <h3 className="text-sm font-semibold text-foreground/60 leading-tight">
          No section selected
        </h3>
        <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-[220px]">
          Click <strong className="text-foreground/70">Edit</strong> on any section in the left
          panel to start editing its content and settings.
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Homepage overview (Col 3 when nothing selected)
// ─────────────────────────────────────────────────────────────────────────────

function HomepageOverview({
  sections,
  onSelect,
}: {
  sections: AdminSection[];
  onSelect: (key: string) => void;
}) {
  const active = sections.filter((s) => s.is_active);
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-none px-4 py-2.5 border-b border-border/40 bg-background/70 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="size-2 rounded-full bg-muted-foreground/30 inline-block" />
          <p className="text-xs font-medium text-foreground/60">Homepage Preview</p>
        </div>
        <p className="text-[10px] text-muted-foreground">{active.length} visible sections</p>
      </div>

      {/* Scrollable section thumbnails */}
      <div className="flex-1 overflow-y-auto bg-white p-4 space-y-3">
        {active.map((section) => (
          <button
            key={section.id}
            onClick={() => onSelect(section.section_key)}
            className="group w-full text-left rounded-lg border border-border/40 overflow-hidden hover:border-primary/50 hover:shadow-md transition-all"
          >
            {/* Section label */}
            <div className="px-3 py-2 flex items-center justify-between bg-muted/20 border-b border-border/30">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground shrink-0">
                  {SECTION_ICONS[section.section_type]}
                </span>
                <span className="text-xs font-medium truncate">
                  {section.title ?? section.section_key}
                </span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded-full border font-medium leading-none shrink-0 ${STATUS_CLS[section.status] ?? STATUS_CLS.published}`}
                >
                  {section.status}
                </span>
              </div>
              <span className="text-[10px] text-primary opacity-0 group-hover:opacity-100 transition-opacity font-semibold uppercase tracking-wide shrink-0">
                Edit →
              </span>
            </div>
            {/* Scaled thumbnail */}
            <div
              className="overflow-hidden"
              style={{
                height: Math.round((NATURAL_H[section.section_type as SectionType] ?? 280) * 0.22),
              }}
            >
              <div
                className="pointer-events-none select-none"
                style={{ width: PREVIEW_W, transform: "scale(0.22)", transformOrigin: "top left" }}
              >
                {renderSection(section, section.config ?? {}, section.items ?? [])}
              </div>
            </div>
          </button>
        ))}
        {active.length === 0 && (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-sm">No visible sections. Enable sections from the left panel.</p>
          </div>
        )}
      </div>

      <div className="flex-none px-4 py-2 border-t border-border/30 bg-background/50">
        <p className="text-[10px] text-muted-foreground/50 text-center">
          Click any section to begin editing
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main editor
// ─────────────────────────────────────────────────────────────────────────────

function AdminCmsEditor() {
  const qc = useQueryClient();
  const { data: sections = [], isLoading } = useCmsSections();
  const reorderMutation = useReorderSections();
  const toggleMutation = useToggleSection();
  const invalidateMutation = useInvalidateCache();

  const saveDraftMutation = useMutation({
    mutationFn: ({ key, config }: { key: string; config: Record<string, unknown> }) =>
      api.patch<AdminSection>(`/cms/admin/sections/${key}/draft`, {
        body: { draft_config: config },
      }),
    onSuccess: (_, { key }) => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(key) });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSections });
    },
  });

  const saveItemsMutation = useMutation({
    mutationFn: async ({
      key,
      items,
      deletedIds,
    }: {
      key: string;
      items: SectionItem[];
      deletedIds: string[];
    }) => {
      // Delete removed items first
      if (deletedIds.length) {
        await Promise.all(
          deletedIds.map((id) => api.delete(`/cms/admin/sections/${key}/items/${id}`)),
        );
      }
      // Create new / update existing
      await Promise.all(
        items.map((it) => {
          if (it.id.startsWith("__")) {
            return api.post(`/cms/admin/sections/${key}/items`, {
              body: { config: it.config, sort_order: it.sort_order, is_enabled: it.is_enabled },
            });
          }
          return api.patch(`/cms/admin/sections/${key}/items/${it.id}`, {
            body: { config: it.config, sort_order: it.sort_order, is_enabled: it.is_enabled },
          });
        }),
      );
    },
    onSuccess: (_, { key }) => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSections });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(key) });
    },
  });

  const publishMutation = useMutation({
    mutationFn: (key: string) =>
      api.post<AdminSection>(`/cms/admin/sections/${key}/publish`, { body: {} }),
    onSuccess: (_, key) => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(key) });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSections });
      qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
    },
  });

  // ── State ─────────────────────────────────────────────────────────────────

  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [localConfigs, setLocalConfigs] = useState<Record<string, Record<string, unknown>>>({});
  const [localItems, setLocalItems] = useState<Record<string, SectionItem[]>>({});
  const [localDeletedItems, setLocalDeletedItems] = useState<Record<string, string[]>>({});
  const [dirtyKeys, setDirtyKeys] = useState<Set<string>>(new Set());

  const [localOrder, setLocalOrder] = useState<AdminSection[]>([]);
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [overIdx, setOverIdx] = useState<number | null>(null);

  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  useEffect(() => {
    if (!statusMsg) return;
    const t = setTimeout(() => setStatusMsg(null), 3500);
    return () => clearTimeout(t);
  }, [statusMsg]);

  useEffect(() => {
    if (dragIdx !== null) return;
    setLocalOrder([...sections].sort((a, b) => a.sort_order - b.sort_order));
  }, [sections, dragIdx]);

  const activeSection = localOrder.find((s) => s.section_key === activeKey) ?? null;

  // ── Config & items helpers ────────────────────────────────────────────────

  function getConfig(section: AdminSection): Record<string, unknown> {
    if (localConfigs[section.section_key] !== undefined) return localConfigs[section.section_key];
    const draft = section.draft_config;
    if (draft && Object.keys(draft).length > 0) return draft;
    const live = section.config;
    if (live && Object.keys(live).length > 0) return live;
    return DEFAULT_CONFIGS[section.section_type as SectionType] ?? {};
  }

  function getItems(section: AdminSection): SectionItem[] {
    if (localItems[section.section_key] !== undefined) return localItems[section.section_key];
    const serverItems = section.items ?? [];
    if (serverItems.length === 0) {
      const defaults = DEFAULT_ITEMS[section.section_type as SectionType];
      if (defaults) {
        return defaults.map((cfg, i) => ({
          id: `__default_${i}`,
          section_id: section.id,
          sort_order: i * 10,
          is_enabled: true,
          config: cfg,
          created_at: "",
          updated_at: "",
        }));
      }
    }
    return serverItems;
  }

  function updateConfig(key: string, config: Record<string, unknown>) {
    setLocalConfigs((prev) => ({ ...prev, [key]: config }));
    setDirtyKeys((prev) => new Set(prev).add(key));
  }

  function handleItemChange(key: string, items: SectionItem[]) {
    setLocalItems((prev) => ({ ...prev, [key]: items }));
    setDirtyKeys((prev) => new Set(prev).add(key));
  }

  function addItem(key: string, cfg: Record<string, unknown>) {
    const section = localOrder.find((s) => s.section_key === key);
    const cur = localItems[key] ?? section?.items ?? [];
    const newItem: SectionItem = {
      id: `__new_${Date.now()}`,
      section_id: section?.id ?? "",
      sort_order: cur.length * 10 + 10,
      is_enabled: true,
      config: cfg,
      created_at: "",
      updated_at: "",
    };
    setLocalItems((prev) => ({ ...prev, [key]: [...cur, newItem] }));
    setDirtyKeys((prev) => new Set(prev).add(key));
  }

  function deleteItem(key: string, itemId: string) {
    const section = localOrder.find((s) => s.section_key === key);
    const cur = localItems[key] ?? section?.items ?? [];
    setLocalItems((prev) => ({ ...prev, [key]: cur.filter((it) => it.id !== itemId) }));
    if (!itemId.startsWith("__")) {
      setLocalDeletedItems((prev) => ({ ...prev, [key]: [...(prev[key] ?? []), itemId] }));
    }
    setDirtyKeys((prev) => new Set(prev).add(key));
  }

  function duplicateItem(key: string, itemId: string) {
    const section = localOrder.find((s) => s.section_key === key);
    const cur = localItems[key] ?? section?.items ?? [];
    const item = cur.find((it) => it.id === itemId);
    if (!item) return;
    const newItem: SectionItem = {
      ...item,
      id: `__new_${Date.now()}`,
      sort_order: cur.length * 10 + 10,
    };
    setLocalItems((prev) => ({ ...prev, [key]: [...cur, newItem] }));
    setDirtyKeys((prev) => new Set(prev).add(key));
  }

  // ── DnD ──────────────────────────────────────────────────────────────────

  const onDragStart = useCallback((idx: number) => {
    setDragIdx(idx);
  }, []);

  const onDragOver = useCallback(
    (idx: number, e: React.DragEvent) => {
      e.preventDefault();
      if (dragIdx === null || dragIdx === idx) return;
      setOverIdx(idx);
      const next = [...localOrder];
      const [item] = next.splice(dragIdx, 1);
      next.splice(idx, 0, item);
      setDragIdx(idx);
      setLocalOrder(next);
    },
    [dragIdx, localOrder],
  );

  const onDrop = useCallback(() => {
    if (dragIdx === null) return;
    const entries = localOrder.map((s, i) => ({ id: s.id, sort_order: i * 10 }));
    reorderMutation.mutate(entries, {
      onError: (e) => {
        toast.error(toUserMessage(e));
        setLocalOrder([...sections].sort((a, b) => a.sort_order - b.sort_order));
      },
    });
    setDragIdx(null);
    setOverIdx(null);
  }, [dragIdx, localOrder, sections, reorderMutation]);

  const handleToggle = useCallback(
    (section: AdminSection) => {
      toggleMutation.mutate(section.section_key, {
        onSuccess: () => setStatusMsg(section.is_active ? "Section hidden" : "Section visible"),
        onError: (e) => toast.error(toUserMessage(e)),
      });
    },
    [toggleMutation],
  );

  const handleSelectSection = useCallback((key: string) => {
    setActiveKey((cur) => (cur === key ? null : key));
  }, []);

  const handleDuplicateStub = useCallback(() => {
    toast.info("Section duplication coming soon.");
  }, []);

  const handleDeleteStub = useCallback(() => {
    toast.info("Section deletion coming soon.");
  }, []);

  // ── Save / Publish / Discard ──────────────────────────────────────────────

  async function handleSaveDraft() {
    if (!activeSection) return;
    const key = activeSection.section_key;
    try {
      await saveDraftMutation.mutateAsync({ key, config: getConfig(activeSection) });
      const currentItems = localItems[key];
      const deletedIds = localDeletedItems[key] ?? [];
      if ((currentItems && currentItems.length > 0) || deletedIds.length > 0) {
        await saveItemsMutation.mutateAsync({ key, items: currentItems ?? [], deletedIds });
      }
      setLocalConfigs((prev) => {
        const n = { ...prev };
        delete n[key];
        return n;
      });
      setLocalItems((prev) => {
        const n = { ...prev };
        delete n[key];
        return n;
      });
      setLocalDeletedItems((prev) => {
        const n = { ...prev };
        delete n[key];
        return n;
      });
      setDirtyKeys((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
      setStatusMsg("Draft saved");
      toast.success("Draft saved.");
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    }
  }

  async function handlePublish() {
    if (!activeSection) return;
    const key = activeSection.section_key;
    try {
      await saveDraftMutation.mutateAsync({ key, config: getConfig(activeSection) });
      const currentItems = localItems[key];
      const deletedIds = localDeletedItems[key] ?? [];
      if ((currentItems && currentItems.length > 0) || deletedIds.length > 0) {
        await saveItemsMutation.mutateAsync({ key, items: currentItems ?? [], deletedIds });
      }
      await publishMutation.mutateAsync(key);
      setLocalConfigs((prev) => {
        const n = { ...prev };
        delete n[key];
        return n;
      });
      setLocalItems((prev) => {
        const n = { ...prev };
        delete n[key];
        return n;
      });
      setLocalDeletedItems((prev) => {
        const n = { ...prev };
        delete n[key];
        return n;
      });
      setDirtyKeys((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
      setStatusMsg("Published · Cache invalidated");
      toast.success("Section published.");
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    }
  }

  function handleDiscard() {
    if (!activeSection) return;
    const key = activeSection.section_key;
    setLocalConfigs((prev) => {
      const n = { ...prev };
      delete n[key];
      return n;
    });
    setLocalItems((prev) => {
      const n = { ...prev };
      delete n[key];
      return n;
    });
    setLocalDeletedItems((prev) => {
      const n = { ...prev };
      delete n[key];
      return n;
    });
    setDirtyKeys((prev) => {
      const n = new Set(prev);
      n.delete(key);
      return n;
    });
    setStatusMsg("Changes discarded");
  }

  function handleFlushCache() {
    invalidateMutation.mutate(undefined, {
      onSuccess: () => {
        setStatusMsg("Cache invalidated");
        toast.success("Cache flushed.");
      },
      onError: (e) => toast.error(toUserMessage(e)),
    });
  }

  const isSaving = saveDraftMutation.isPending || saveItemsMutation.isPending;
  const isPublishing = publishMutation.isPending;
  const totalDirty = dirtyKeys.size;

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div
      className="-mx-6 -my-6 md:-mx-10 md:-my-10 flex flex-col bg-secondary/20"
      style={{ height: "100vh" }}
    >
      {/* Top bar */}
      <div className="flex-none h-14 border-b border-border/60 bg-background flex items-center justify-between px-5 gap-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Settings className="size-4" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight">Homepage CMS</p>
            <p className="text-[10px] text-muted-foreground leading-tight">Visual editor</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {totalDirty > 0 && (
            <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-1 rounded-full">
              {totalDirty} unsaved {totalDirty === 1 ? "section" : "sections"}
            </span>
          )}
          <a
            href="/"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground border border-border/60 px-3 py-1.5 rounded-lg hover:bg-muted transition-colors"
          >
            <ExternalLink className="size-3.5" /> Preview Store
          </a>
          <Link
            to="/admin/cms/media"
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground border border-border/60 px-3 py-1.5 rounded-lg hover:bg-muted transition-colors"
          >
            Media Library
          </Link>
          {activeSection && dirtyKeys.has(activeSection.section_key) && (
            <button
              onClick={handleDiscard}
              className="text-xs text-muted-foreground border border-border/60 px-3 py-1.5 rounded-lg hover:bg-muted transition-colors"
            >
              Discard
            </button>
          )}
          <button
            onClick={handleFlushCache}
            disabled={invalidateMutation.isPending}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground border border-border/60 px-3 py-1.5 rounded-lg hover:bg-muted disabled:opacity-50 transition-colors"
          >
            <RefreshCw className="size-3.5" /> Flush Cache
          </button>
          {activeSection && (
            <>
              <button
                onClick={handleSaveDraft}
                disabled={isSaving || !dirtyKeys.has(activeSection.section_key)}
                className="inline-flex items-center gap-1.5 text-xs border border-border px-3 py-1.5 rounded-lg hover:bg-muted disabled:opacity-40 transition-colors"
              >
                <Save className="size-3.5" /> Save Draft
              </button>
              <button
                onClick={handlePublish}
                disabled={isPublishing}
                className="inline-flex items-center gap-1.5 text-xs bg-primary text-primary-foreground px-3 py-1.5 rounded-lg hover:bg-primary/90 disabled:opacity-60 transition-colors"
              >
                <Zap className="size-3.5" /> Publish
              </button>
            </>
          )}
        </div>
      </div>

      {/* Body — 3 columns, each scrolls independently */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* ── Col 1: Sections list (320px) ── */}
        <div className="w-[320px] shrink-0 flex flex-col border-r border-border/50 bg-muted/10 overflow-hidden">
          <div className="flex-none px-4 pt-3.5 pb-2.5 border-b border-border/40">
            <p className="text-[10px] uppercase tracking-[0.25em] font-semibold text-muted-foreground">
              Sections
            </p>
            <p className="text-[11px] text-muted-foreground/70 mt-0.5">
              Drag to reorder · click Edit to configure
            </p>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-[72px] rounded-xl" />
              ))}
            {localOrder.map((section, idx) => (
              <SectionCard
                key={section.id}
                section={section}
                idx={idx}
                isActive={activeKey === section.section_key}
                isDragging={dragIdx === idx}
                isOver={overIdx === idx}
                isDirty={dirtyKeys.has(section.section_key)}
                onSelect={handleSelectSection}
                onToggle={handleToggle}
                onDragStart={onDragStart}
                onDragOver={onDragOver}
                onDrop={onDrop}
                onDuplicate={handleDuplicateStub}
                onDelete={handleDeleteStub}
              />
            ))}
            {!isLoading && localOrder.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-8">No sections found.</p>
            )}
          </div>
        </div>

        {/* ── Col 2: Section editor — form controls only (500px) ── */}
        <div className="w-[500px] shrink-0 flex flex-col border-r border-border/50 overflow-hidden bg-background">
          {activeSection ? (
            <SectionEditorPanel
              section={activeSection}
              config={getConfig(activeSection)}
              onChange={(c) => updateConfig(activeSection.section_key, c)}
              items={getItems(activeSection)}
              onItemChange={(items) => handleItemChange(activeSection.section_key, items)}
              onAddItem={(cfg) => addItem(activeSection.section_key, cfg)}
              onDeleteItem={(id) => deleteItem(activeSection.section_key, id)}
              onDuplicateItem={(id) => duplicateItem(activeSection.section_key, id)}
              onSaveDraft={handleSaveDraft}
              onPublish={handlePublish}
              onClose={() => setActiveKey(null)}
              isSaving={isSaving}
              isPublishing={isPublishing}
              isDirty={dirtyKeys.has(activeSection.section_key)}
            />
          ) : (
            <EditorEmptyState />
          )}
        </div>

        {/* ── Col 3: Live preview — storefront component, no controls (flex-1) ── */}
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
          {activeSection ? (
            <PreviewPanel
              section={activeSection}
              config={getConfig(activeSection)}
              items={getItems(activeSection)}
              isDirty={dirtyKeys.has(activeSection.section_key)}
            />
          ) : (
            <HomepageOverview sections={localOrder} onSelect={(key) => setActiveKey(key)} />
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex-none h-8 border-t border-border/40 bg-muted/30 flex items-center px-5 gap-3">
        <div className="flex items-center gap-1.5">
          {statusMsg ? (
            <>
              <Check className="size-3 text-emerald-600" />
              <span className="text-[11px] text-emerald-700">{statusMsg}</span>
            </>
          ) : (
            <>
              <span className="size-1.5 rounded-full bg-emerald-400 inline-block" />
              <span className="text-[11px] text-muted-foreground">Ready</span>
            </>
          )}
        </div>
        {totalDirty > 0 && (
          <span className="text-[11px] text-amber-600">· {totalDirty} unsaved</span>
        )}
        {(isSaving || isPublishing) && (
          <span className="text-[11px] text-muted-foreground animate-pulse">
            · {isSaving ? "Saving…" : "Publishing…"}
          </span>
        )}
        <div className="ml-auto text-[11px] text-muted-foreground">Hadha Homepage CMS</div>
      </div>
    </div>
  );
}
