import { useState, useRef, useCallback, useEffect, useId, useMemo } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronUp,
  Plus,
  Trash2,
  RefreshCw,
  Upload,
  X,
  ImageIcon,
  AlertCircle,
  Star,
  Sparkles,
  Crop as CropIcon,
  ImagePlus,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import {
  UniversalImageEditor,
  uploadImage,
  cropImage,
  replaceImage,
  deleteImage as deleteMediaImage,
  setPrimaryImage,
  getImage,
  pollImageUntilReady,
  bustCacheUrl,
  regenerateImage,
  reorderImages,
  updateImageAltText,
  validateFileResolution,
  type ImageOutRaw,
  type SaveIntent,
  type UniversalImageEditorSaveResult,
} from "@hadha/shared-media";
import { PRESET_REGISTRY } from "@hadha/shared-types";
import type { Breakpoint, BreakpointCropGeometry, CropGeometry } from "@hadha/shared-types";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@hadha/shared-ui/ui/dialog";
import type {
  CategoryTreeNode,
  CollectionDetail,
  CollectionListItem,
  CollectionListResponse,
  ProductDetail,
  ProductStatus,
  ProductImage,
  ProductVariant,
} from "@/types/admin";

const PRODUCT_PRESET = PRESET_REGISTRY.product;

/** Converts the media API's ImageOut shape into the flat ProductImage shape
 * the rest of this form (and the storefront) expects — mirrors exactly what
 * Backend/app/modules/catalog/schemas.py's ProductImageResponse.from_image()
 * does server-side, since the universal media endpoints return ImageOut,
 * not ProductImageResponse. */
function mapImageOutToProductImage(raw: ImageOutRaw): ProductImage {
  const ready = raw.variants.filter(
    (v) => v.breakpoint === "desktop" && v.dpr === 1 && v.status === "ready",
  );
  const byName = (name: string) => ready.find((v) => v.variant_name === name)?.url ?? null;
  const cropDesktop = raw.metadata.crops?.desktop as
    | {
        box: { x: number; y: number; width: number; height: number };
        zoom: number;
        rotation: number;
      }
    | undefined;
  const large = byName("large");
  const medium = byName("medium");
  return {
    id: raw.id,
    url: large ?? medium ?? byName("thumbnail") ?? "",
    original_url: raw.original_url,
    thumbnail_url: byName("thumbnail"),
    medium_url: medium,
    large_url: large,
    alt_text: raw.alt_text,
    is_primary: raw.is_primary,
    sort_order: raw.sort_order,
    crop_x: cropDesktop?.box.x ?? null,
    crop_y: cropDesktop?.box.y ?? null,
    crop_width: cropDesktop?.box.width ?? null,
    crop_height: cropDesktop?.box.height ?? null,
    crop_zoom: cropDesktop?.zoom ?? null,
    crop_rotation: cropDesktop?.rotation ?? null,
    updated_at: raw.updated_at,
  };
}

/** Parses ImageOutRaw's metadata.crops back into the shape UniversalImageEditor
 * seeds itself from, across every breakpoint the product preset defines —
 * mirrors CollectionForm/CategoryForm's equivalent. `ProductImage` (the flat
 * shape used elsewhere in this form) only carries desktop crop columns, so
 * re-editing an existing image must go through this + a fresh `getImage`
 * fetch rather than `mapImageOutToProductImage`, or tablet/mobile framing
 * gets silently reset to centered defaults and overwritten on save. */
function parseStoredCrops(
  raw: ImageOutRaw,
): Partial<Record<Breakpoint, BreakpointCropGeometry>> | undefined {
  const crops = raw.metadata.crops as
    | Record<
        string,
        {
          box: { x: number; y: number; width: number; height: number };
          zoom: number;
          rotation: number;
        }
      >
    | undefined;
  if (!crops) return undefined;
  const result: Partial<Record<Breakpoint, BreakpointCropGeometry>> = {};
  for (const bp of PRODUCT_PRESET.breakpoints) {
    const c = crops[bp];
    if (!c) continue;
    result[bp] = {
      aspectRatio: PRODUCT_PRESET.aspectRatio[bp] ?? null,
      box: c.box,
      zoom: c.zoom,
      pan: { x: 0, y: 0 },
      rotation: c.rotation,
    };
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

// ─── Local types ──────────────────────────────────────────────────────────────

interface VariantOption {
  id: string;
  name: string;
  values: string[];
  newValue: string;
}

interface LocalVariant {
  id: string;
  sku: string;
  name: string;
  price_adjustment: number;
  stock_quantity: number;
  weight_grams: number | null;
  is_active: boolean;
}

interface LocalAttribute {
  id: string;
  name: string;
  value: string;
}

interface PendingImage {
  id: string;
  file: File;
  preview: string;
  alt_text: string;
  /** Set once the admin has cropped this image in the editor; applied right
   * after the file is uploaded. NULL means "upload as-is" (backward
   * compatible with the pre-cropping flow). */
  crop: CropGeometry | null;
}

/** Which image is currently open in the crop editor, and where its bytes
 * live (a local blob for not-yet-uploaded images, the R2 original for
 * already-saved ones). Each image crops independently of the others. */
type CropTarget = { kind: "pending"; id: string } | { kind: "saved"; id: string };

interface FormState {
  name: string;
  slug: string;
  sku: string;
  short_description: string;
  description: string;
  status: ProductStatus;
  parent_category_id: string;
  category_id: string;
  collection_ids: string[];
  base_price: string;
  compare_at_price: string;
  cost_price: string;
  tax_rate: string;
  hsn_code: string;
  track_inventory: boolean;
  stock_quantity: string;
  low_stock_threshold: string;
  allow_backorder: boolean;
  metal_type: string;
  purity: string;
  hallmark_number: string;
  making_charges: string;
  wastage_percent: string;
  weight_grams: string;
  gender: string;
  is_customizable: boolean;
  requires_shipping: boolean;
  length_cm: string;
  width_cm: string;
  height_cm: string;
  is_featured: boolean;
  is_new_arrival: boolean;
  is_best_seller: boolean;
  meta_title: string;
  meta_description: string;
  meta_keywords: string;
  enable_variants: boolean;
  variant_options: VariantOption[];
  variants: LocalVariant[];
  attributes: LocalAttribute[];
}

type FormErrors = Record<string, string>;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

function getCategoryPrefix(name: string): string {
  const clean = name.replace(/[^a-zA-Z]/g, "");
  return (clean.slice(0, 2) || "XX").toUpperCase();
}

function cartesian<T>(arrays: T[][]): T[][] {
  if (arrays.length === 0) return [[]];
  const [first, ...rest] = arrays;
  const restCombos = cartesian(rest);
  return first.flatMap((v) => restCombos.map((combo) => [v, ...combo]));
}

function uid(): string {
  return `__new_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

function emptyForm(): FormState {
  return {
    name: "",
    slug: "",
    sku: "",
    short_description: "",
    description: "",
    status: "draft",
    parent_category_id: "",
    category_id: "",
    collection_ids: [],
    base_price: "",
    compare_at_price: "",
    cost_price: "",
    tax_rate: "3",
    hsn_code: "7113",
    track_inventory: true,
    stock_quantity: "0",
    low_stock_threshold: "5",
    allow_backorder: false,
    metal_type: "925 Silver",
    purity: "925",
    hallmark_number: "",
    making_charges: "",
    wastage_percent: "",
    weight_grams: "",
    gender: "",
    is_customizable: false,
    requires_shipping: true,
    length_cm: "",
    width_cm: "",
    height_cm: "",
    is_featured: false,
    is_new_arrival: false,
    is_best_seller: false,
    meta_title: "",
    meta_description: "",
    meta_keywords: "",
    enable_variants: false,
    variant_options: [],
    variants: [],
    attributes: [],
  };
}

function productToForm(p: ProductDetail, categoryTree: CategoryTreeNode[]): FormState {
  const parentId =
    categoryTree.find((n) => n.children.some((c) => c.id === p.category_id))?.id ??
    p.category_id ??
    "";

  return {
    name: p.name,
    slug: p.slug,
    sku: p.sku,
    short_description: p.short_description ?? "",
    description: p.description ?? "",
    status: p.status,
    parent_category_id: parentId,
    category_id: p.category_id ?? "",
    collection_ids: [],
    base_price: String(p.base_price),
    compare_at_price: p.compare_at_price ? String(p.compare_at_price) : "",
    cost_price: p.cost_price ? String(p.cost_price) : "",
    tax_rate: String(p.tax_rate),
    hsn_code: p.hsn_code ?? "7113",
    track_inventory: p.track_inventory,
    stock_quantity: String(p.stock_quantity),
    low_stock_threshold: String(p.low_stock_threshold),
    allow_backorder: p.allow_backorder,
    metal_type: p.metal_type ?? "925 Silver",
    purity: p.purity ?? "925",
    hallmark_number: p.hallmark_number ?? "",
    making_charges: p.making_charges ? String(p.making_charges) : "",
    wastage_percent: p.wastage_percent ? String(p.wastage_percent) : "",
    weight_grams: p.weight_grams ? String(p.weight_grams) : "",
    gender: p.gender ?? "",
    is_customizable: p.is_customizable,
    requires_shipping: p.requires_shipping,
    length_cm: p.length_cm ? String(p.length_cm) : "",
    width_cm: p.width_cm ? String(p.width_cm) : "",
    height_cm: p.height_cm ? String(p.height_cm) : "",
    is_featured: p.is_featured,
    is_new_arrival: p.is_new_arrival,
    is_best_seller: p.is_best_seller,
    meta_title: p.meta_title ?? "",
    meta_description: p.meta_description ?? "",
    meta_keywords: p.meta_keywords ?? "",
    enable_variants: p.variants.length > 0,
    variant_options: [],
    variants: p.variants.map((v) => ({
      id: v.id,
      sku: v.sku,
      name: v.name,
      price_adjustment: v.price_adjustment,
      stock_quantity: v.stock_quantity,
      weight_grams: v.weight_grams,
      is_active: v.is_active,
    })),
    attributes: p.attributes.map((a) => ({
      id: a.id,
      name: a.name,
      value: a.value,
    })),
  };
}

function validateForm(
  form: FormState,
  pendingImages: PendingImage[],
  savedImages: ProductImage[],
): FormErrors {
  const e: FormErrors = {};
  if (!form.name.trim()) e.name = "Product name is required";
  if (!form.sku.trim()) e.sku = "SKU is required";
  if (!form.slug.trim()) e.slug = "Slug is required";
  if (!form.short_description.trim()) e.short_description = "Short description is required";
  if (!form.description.trim()) e.description = "Description is required";
  if (!form.category_id) e.category_id = "Sub-category is required";
  if (!form.base_price || parseFloat(form.base_price) <= 0) e.base_price = "Base price must be > 0";
  if (pendingImages.length === 0 && savedImages.length === 0)
    e.images = "At least one image is required";
  return e;
}

// ─── SEO generation helpers ───────────────────────────────────────────────────

function generateMetaTitle(name: string, metalType: string, purity: string): string {
  const n = name.trim();
  if (!n) return "";
  const BRAND = "Hadha";
  const metal = metalType.trim();
  const pur = purity.trim();
  const metalStr =
    metal && pur && !metal.toLowerCase().startsWith(pur.toLowerCase()) ? `${pur} ${metal}` : metal;

  const withMetal = metalStr ? `${n} | ${metalStr} | ${BRAND}` : `${n} | ${BRAND}`;
  if (withMetal.length <= 60) return withMetal;

  const withoutMetal = `${n} | ${BRAND}`;
  if (withoutMetal.length <= 60) return withoutMetal;

  // Trim name intelligently — never cut mid-word
  const suffix = ` | ${BRAND}`;
  const available = 60 - suffix.length;
  let trimmed = n.slice(0, available);
  const lastSpace = trimmed.lastIndexOf(" ");
  if (lastSpace > available / 2) trimmed = trimmed.slice(0, lastSpace);
  return trimmed + suffix;
}

function generateMetaDescription(
  shortDesc: string,
  description: string,
  name: string,
  categoryName: string,
  metalType: string,
): string {
  const source = (shortDesc || description || "").replace(/\s+/g, " ").trim();
  if (!source) {
    const parts = [name, categoryName, metalType].filter(Boolean);
    const base = parts.join(", ");
    return (base + ". Shop authentic silver jewellery at Hadha.").slice(0, 160);
  }

  if (source.length >= 120 && source.length <= 160) return source;

  if (source.length > 160) {
    const at160 = source.slice(0, 160);
    const lastDot = at160.lastIndexOf(".");
    if (lastDot >= 100) return source.slice(0, lastDot + 1);
    const lastSpace = at160.lastIndexOf(" ");
    return at160.slice(0, lastSpace > 0 ? lastSpace : 160).replace(/[,;:]$/, "") + ".";
  }

  // Under 120 — append brand tagline if it fits
  const tagline = " Shop authentic silver jewellery at Hadha.";
  const extended = source + tagline;
  return extended.length <= 160 ? extended : source;
}

function generateMetaKeywords(
  name: string,
  categoryName: string,
  collectionNames: string[],
  gender: string,
  metalType: string,
  purity: string,
): string {
  const seen = new Set<string>();
  const kws: string[] = [];

  const add = (kw: string) => {
    const k = kw.toLowerCase().trim();
    if (k && k.length > 1 && !seen.has(k)) {
      seen.add(k);
      kws.push(k);
    }
  };

  const nameLower = name.toLowerCase().trim();
  const catLower = categoryName.toLowerCase().trim();
  const metalLower = metalType.toLowerCase().trim();
  const purStr = purity.trim();

  if (nameLower) add(nameLower);

  if (purStr && metalLower) {
    const combined = metalLower.startsWith(purStr.toLowerCase())
      ? metalLower
      : `${purStr} ${metalLower}`;
    add(combined);
    add(`${purStr} silver`);
    add("sterling silver");
  } else if (metalLower) {
    add(metalLower);
  }

  if (catLower) {
    add(catLower);
    if (purStr) add(`${purStr} ${catLower}`);
  }

  if (nameLower && catLower) {
    const nameWords = nameLower.split(/\s+/);
    if (nameWords.length > 1) add(`${nameWords.slice(0, 2).join(" ")} ${catLower}`);
  }

  if (gender && catLower) {
    add(`${gender} ${catLower}`);
    if (purStr) add(`${gender} ${purStr} ${catLower}`);
  }

  collectionNames.forEach((c) => add(c));

  add("silver jewellery");
  add("hadha jewellery");

  return kws.slice(0, 15).join(", ");
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({
  title,
  children,
  defaultOpen = true,
  error = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  error?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border bg-background">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 text-left"
      >
        <span
          className={`text-[11px] uppercase tracking-[0.22em] font-medium ${error ? "text-destructive" : ""}`}
        >
          {error && <AlertCircle className="inline size-3.5 mr-1.5 -mt-0.5" />}
          {title}
        </span>
        {open ? (
          <ChevronUp className="size-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 text-muted-foreground" />
        )}
      </button>
      {open && <div className="px-5 pb-5 border-t border-border">{children}</div>}
    </div>
  );
}

// ─── Field helpers ────────────────────────────────────────────────────────────

function Field({
  label,
  error,
  required,
  hint,
  children,
  id,
}: {
  label: string;
  error?: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
  id?: string;
}) {
  return (
    <div id={id} className="flex flex-col gap-1.5">
      <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        {label}
        {required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      {children}
      {hint && !error && <p className="text-[11px] text-muted-foreground">{hint}</p>}
      {error && <p className="text-[11px] text-destructive">{error}</p>}
    </div>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
  error,
  disabled,
  type = "text",
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  error?: boolean;
  disabled?: boolean;
  type?: string;
  className?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={`border px-3 py-2 bg-transparent text-sm outline-none w-full ${
        error ? "border-destructive" : "border-border"
      } disabled:opacity-50 ${className}`}
    />
  );
}

function ToggleSwitch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative w-9 h-5 rounded-full transition-colors ${
          checked ? "bg-primary" : "bg-border"
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-background shadow transition-transform ${
            checked ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </button>
      <span className="text-sm">{label}</span>
    </label>
  );
}

// ─── Dialogs ──────────────────────────────────────────────────────────────────

function CreateCategoryDialog({
  parentId,
  parentName,
  onCreated,
  onClose,
}: {
  parentId: string;
  parentName: string;
  onCreated: (cat: CategoryTreeNode) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [desc, setDesc] = useState("");
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const result = await api.post<CategoryTreeNode>("/admin/categories", {
        body: {
          name: name.trim(),
          slug: slug || toSlug(name),
          description: desc || undefined,
          parent_id: parentId || undefined,
          is_active: true,
        },
      });
      toast.success("Category created.");
      onCreated({ ...result, children: [], product_count: 0 });
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-background border border-border w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-[11px] uppercase tracking-[0.22em] font-medium">Create Category</h2>
          <button type="button" onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        {parentId && (
          <p className="text-xs text-muted-foreground mb-4">
            Under: <strong>{parentName}</strong>
          </p>
        )}
        <div className="flex flex-col gap-4">
          <Field label="Name" required>
            <TextInput
              value={name}
              onChange={(v) => {
                setName(v);
                setSlug(toSlug(v));
              }}
              placeholder="e.g. Rings"
            />
          </Field>
          <Field label="Slug" hint="Auto-generated, editable">
            <TextInput value={slug} onChange={setSlug} placeholder="e.g. rings" />
          </Field>
          <Field label="Description">
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              rows={3}
              className="border border-border px-3 py-2 bg-transparent text-sm outline-none w-full resize-none"
            />
          </Field>
        </div>
        <div className="flex gap-3 mt-6">
          <button
            type="button"
            onClick={handleCreate}
            disabled={!name.trim() || saving}
            className="flex-1 flex items-center justify-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-2.5 disabled:opacity-50"
          >
            {saving && <Loader2 className="size-3.5 animate-spin" />}
            {saving ? "Creating…" : "Create"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 border border-border text-[11px] uppercase tracking-[0.22em]"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function CreateCollectionDialog({
  onCreated,
  onClose,
}: {
  onCreated: (col: CollectionDetail) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [desc, setDesc] = useState("");
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const result = await api.post<CollectionDetail>("/admin/collections", {
        body: {
          name: name.trim(),
          slug: slug || toSlug(name),
          description: desc || undefined,
          is_active: true,
          is_featured: false,
        },
      });
      toast.success("Collection created.");
      onCreated(result);
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-background border border-border w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-[11px] uppercase tracking-[0.22em] font-medium">Create Collection</h2>
          <button type="button" onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="flex flex-col gap-4">
          <Field label="Name" required>
            <TextInput
              value={name}
              onChange={(v) => {
                setName(v);
                setSlug(toSlug(v));
              }}
              placeholder="e.g. Summer Edit"
            />
          </Field>
          <Field label="Slug" hint="Auto-generated, editable">
            <TextInput value={slug} onChange={setSlug} placeholder="e.g. summer-edit" />
          </Field>
          <Field label="Description">
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              rows={3}
              className="border border-border px-3 py-2 bg-transparent text-sm outline-none w-full resize-none"
            />
          </Field>
        </div>
        <div className="flex gap-3 mt-6">
          <button
            type="button"
            onClick={handleCreate}
            disabled={!name.trim() || saving}
            className="flex-1 flex items-center justify-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-2.5 disabled:opacity-50"
          >
            {saving && <Loader2 className="size-3.5 animate-spin" />}
            {saving ? "Creating…" : "Create"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 border border-border text-[11px] uppercase tracking-[0.22em]"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Product Information Section ───────────────────────────────────────────────

function ProductInfoSection({
  form,
  set,
  errors,
  onGenerateSku,
  skuLoading,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
  errors: FormErrors;
  onGenerateSku: () => void;
  skuLoading: boolean;
}) {
  const slugManualRef = useRef(false);

  const handleNameChange = (v: string) => {
    const patch: Partial<FormState> = { name: v };
    if (!slugManualRef.current) patch.slug = toSlug(v);
    set(patch);
  };

  return (
    <div className="flex flex-col gap-5 pt-5">
      <Field label="Product Name" required error={errors.name} id="name">
        <TextInput
          value={form.name}
          onChange={handleNameChange}
          placeholder="e.g. 925 Silver Twisted Ring"
          error={!!errors.name}
        />
      </Field>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Slug" required error={errors.slug} id="slug" hint="Auto-generated · editable">
          <div className="flex gap-2">
            <TextInput
              value={form.slug}
              onChange={(v) => {
                slugManualRef.current = true;
                set({ slug: v });
              }}
              placeholder="product-slug"
              error={!!errors.slug}
            />
            <button
              type="button"
              onClick={() => {
                slugManualRef.current = false;
                set({ slug: toSlug(form.name) });
              }}
              title="Regenerate from name"
              className="shrink-0 border border-border px-3 hover:bg-secondary"
            >
              <RefreshCw className="size-3.5" />
            </button>
          </div>
        </Field>

        <Field label="SKU" required error={errors.sku} id="sku" hint={`e.g. HDH-RG-000001`}>
          <div className="flex gap-2">
            <TextInput
              value={form.sku}
              onChange={(v) => set({ sku: v })}
              placeholder="HDH-XX-000001"
              error={!!errors.sku}
              className="font-mono"
            />
            <button
              type="button"
              onClick={onGenerateSku}
              disabled={skuLoading}
              title="Auto-generate SKU"
              className="shrink-0 border border-border px-3 hover:bg-secondary disabled:opacity-50"
            >
              <RefreshCw className={`size-3.5 ${skuLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </Field>
      </div>

      <Field
        label="Short Description"
        required
        error={errors.short_description}
        id="short_description"
        hint={`${form.short_description.length}/500`}
      >
        <textarea
          value={form.short_description}
          onChange={(e) => set({ short_description: e.target.value })}
          maxLength={500}
          rows={2}
          placeholder="Brief product summary for listings…"
          className={`border px-3 py-2 bg-transparent text-sm outline-none w-full resize-none ${
            errors.short_description ? "border-destructive" : "border-border"
          }`}
        />
      </Field>

      <Field
        label="Description"
        required
        error={errors.description}
        id="description"
        hint={`${form.description.length} chars`}
      >
        <textarea
          value={form.description}
          onChange={(e) => set({ description: e.target.value })}
          rows={6}
          placeholder="Full product description…"
          className={`border px-3 py-2 bg-transparent text-sm outline-none w-full resize-none ${
            errors.description ? "border-destructive" : "border-border"
          }`}
        />
      </Field>

      <div className="grid grid-cols-3 gap-3">
        {(["is_featured", "is_new_arrival", "is_best_seller"] as const).map((key) => (
          <label key={key} className="flex items-center gap-2 cursor-pointer text-sm">
            <input
              type="checkbox"
              checked={form[key]}
              onChange={(e) => set({ [key]: e.target.checked })}
              className="accent-primary size-4"
            />
            {key === "is_featured"
              ? "Featured"
              : key === "is_new_arrival"
                ? "New Arrival"
                : "Best Seller"}
          </label>
        ))}
      </div>
    </div>
  );
}

// ─── Organization Section ─────────────────────────────────────────────────────

function OrganizationSection({
  form,
  set,
  errors,
  categoryTree,
  collections,
  onCategoryCreated,
  onCollectionCreated,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
  errors: FormErrors;
  categoryTree: CategoryTreeNode[];
  collections: CollectionListItem[];
  onCategoryCreated: (cat: CategoryTreeNode) => void;
  onCollectionCreated: (col: CollectionDetail) => void;
}) {
  const [showCreateCategory, setShowCreateCategory] = useState(false);
  const [showCreateCollection, setShowCreateCollection] = useState(false);

  const parentCategories = categoryTree;
  const subCategories = form.parent_category_id
    ? (parentCategories.find((p) => p.id === form.parent_category_id)?.children ?? [])
    : [];

  const selectedParentName =
    parentCategories.find((p) => p.id === form.parent_category_id)?.name ?? "";

  const toggleCollection = (id: string) => {
    set({
      collection_ids: form.collection_ids.includes(id)
        ? form.collection_ids.filter((c) => c !== id)
        : [...form.collection_ids, id],
    });
  };

  return (
    <div className="flex flex-col gap-5 pt-5">
      <Field label="Parent Category" required>
        <select
          value={form.parent_category_id}
          onChange={(e) => set({ parent_category_id: e.target.value, category_id: "" })}
          className="border border-border px-3 py-2 bg-background text-sm outline-none w-full"
        >
          <option value="">Select parent category…</option>
          {parentCategories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </Field>

      {form.parent_category_id && (
        <Field label="Sub Category" required error={errors.category_id} id="category_id">
          <div className="flex gap-2">
            <select
              value={form.category_id}
              onChange={(e) => set({ category_id: e.target.value })}
              className={`flex-1 border px-3 py-2 bg-background text-sm outline-none ${
                errors.category_id ? "border-destructive" : "border-border"
              }`}
            >
              <option value="">Select sub-category…</option>
              {subCategories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setShowCreateCategory(true)}
              className="shrink-0 border border-border px-3 text-[11px] uppercase tracking-[0.18em] hover:bg-secondary whitespace-nowrap"
            >
              + Create
            </button>
          </div>
        </Field>
      )}

      {!form.parent_category_id && (
        <button
          type="button"
          onClick={() => setShowCreateCategory(true)}
          className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground text-left"
        >
          + Create Category
        </button>
      )}

      <Field label="Collections" hint="Product can belong to multiple collections">
        <div className="flex flex-col gap-2 max-h-48 overflow-y-auto border border-border p-2">
          {collections.length === 0 && (
            <p className="text-xs text-muted-foreground px-1">No collections yet.</p>
          )}
          {collections.map((col) => (
            <label
              key={col.id}
              className="flex items-center gap-2.5 cursor-pointer px-1 py-0.5 hover:bg-secondary/50"
            >
              <input
                type="checkbox"
                checked={form.collection_ids.includes(col.id)}
                onChange={() => toggleCollection(col.id)}
                className="accent-primary size-4 shrink-0"
              />
              <span className="text-sm">{col.name}</span>
              {!col.is_active && (
                <span className="text-[10px] text-muted-foreground ml-auto">(inactive)</span>
              )}
            </label>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setShowCreateCollection(true)}
          className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground text-left mt-1"
        >
          + Create Collection
        </button>
      </Field>

      {showCreateCategory && (
        <CreateCategoryDialog
          parentId={form.parent_category_id}
          parentName={selectedParentName}
          onCreated={(cat) => {
            onCategoryCreated(cat);
            if (form.parent_category_id) {
              set({ category_id: cat.id });
            } else {
              set({ parent_category_id: cat.id });
            }
            setShowCreateCategory(false);
          }}
          onClose={() => setShowCreateCategory(false)}
        />
      )}
      {showCreateCollection && (
        <CreateCollectionDialog
          onCreated={(col) => {
            onCollectionCreated(col);
            set({ collection_ids: [...form.collection_ids, col.id] });
            setShowCreateCollection(false);
          }}
          onClose={() => setShowCreateCollection(false)}
        />
      )}
    </div>
  );
}

// ─── Pricing Section ──────────────────────────────────────────────────────────

function PricingSection({
  form,
  set,
  errors,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
  errors: FormErrors;
}) {
  const base = parseFloat(form.base_price) || 0;
  const compare = parseFloat(form.compare_at_price) || 0;
  const taxRate = parseFloat(form.tax_rate) || 3;
  const discountPct =
    compare > base && compare > 0 ? Math.round(((compare - base) / compare) * 100) : 0;
  const taxAmount = base * (taxRate / 100);
  const priceIncTax = base + taxAmount;

  return (
    <div className="flex flex-col gap-5 pt-5">
      <div className="grid grid-cols-2 gap-4">
        <Field label="Base Price (₹)" required error={errors.base_price} id="base_price">
          <TextInput
            type="number"
            value={form.base_price}
            onChange={(v) => set({ base_price: v })}
            placeholder="0.00"
            error={!!errors.base_price}
          />
        </Field>
        <Field label="Compare-at Price (₹)" hint="Show original/MRP price">
          <TextInput
            type="number"
            value={form.compare_at_price}
            onChange={(v) => set({ compare_at_price: v })}
            placeholder="0.00"
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Cost Price (₹)" hint="Your cost · not shown to customers">
          <TextInput
            type="number"
            value={form.cost_price}
            onChange={(v) => set({ cost_price: v })}
            placeholder="0.00"
          />
        </Field>
        <Field label="GST %" hint="Default 3% for silver jewellery">
          <TextInput
            type="number"
            value={form.tax_rate}
            onChange={(v) => set({ tax_rate: v })}
            placeholder="3"
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="HSN Code" hint="Default 7113 for jewellery">
          <TextInput
            value={form.hsn_code}
            onChange={(v) => set({ hsn_code: v })}
            placeholder="7113"
          />
        </Field>
      </div>

      {base > 0 && (
        <div className="bg-secondary/40 border border-border p-4 flex gap-6 text-sm">
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Selling Price
            </p>
            <p className="font-display text-lg mt-0.5">{formatINR(base)}</p>
          </div>
          {compare > 0 && discountPct > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Discount
              </p>
              <p className="font-display text-lg mt-0.5 text-accent">{discountPct}% off</p>
            </div>
          )}
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Inc. GST ({taxRate}%)
            </p>
            <p className="font-display text-lg mt-0.5">{formatINR(priceIncTax)}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Inventory Section ────────────────────────────────────────────────────────

function InventorySection({
  form,
  set,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
}) {
  return (
    <div className="flex flex-col gap-5 pt-5">
      <ToggleSwitch
        checked={form.track_inventory}
        onChange={(v) => set({ track_inventory: v })}
        label="Track inventory"
      />

      {form.track_inventory && (
        <div className="grid grid-cols-2 gap-4">
          <Field label="Stock Quantity" required>
            <TextInput
              type="number"
              value={form.stock_quantity}
              onChange={(v) => set({ stock_quantity: v })}
              placeholder="0"
            />
          </Field>
          <Field label="Low Stock Alert" hint="Alert when stock falls below">
            <TextInput
              type="number"
              value={form.low_stock_threshold}
              onChange={(v) => set({ low_stock_threshold: v })}
              placeholder="5"
            />
          </Field>
        </div>
      )}

      <ToggleSwitch
        checked={form.allow_backorder}
        onChange={(v) => set({ allow_backorder: v })}
        label="Allow backorders (sell when out of stock)"
      />
    </div>
  );
}

// ─── Jewellery Details Section ────────────────────────────────────────────────

function JewellerySection({
  form,
  set,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
}) {
  return (
    <div className="flex flex-col gap-5 pt-5">
      <div className="grid grid-cols-2 gap-4">
        <Field label="Metal Type">
          <TextInput
            value={form.metal_type}
            onChange={(v) => set({ metal_type: v })}
            placeholder="925 Silver"
          />
        </Field>
        <Field label="Purity">
          <TextInput value={form.purity} onChange={(v) => set({ purity: v })} placeholder="925" />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Hallmark Number">
          <TextInput
            value={form.hallmark_number}
            onChange={(v) => set({ hallmark_number: v })}
            placeholder="BIS Hallmark ID"
          />
        </Field>
        <Field label="Weight (g)">
          <TextInput
            type="number"
            value={form.weight_grams}
            onChange={(v) => set({ weight_grams: v })}
            placeholder="0.00"
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Making Charges (₹)">
          <TextInput
            type="number"
            value={form.making_charges}
            onChange={(v) => set({ making_charges: v })}
            placeholder="0.00"
          />
        </Field>
        <Field label="Wastage %">
          <TextInput
            type="number"
            value={form.wastage_percent}
            onChange={(v) => set({ wastage_percent: v })}
            placeholder="0"
          />
        </Field>
      </div>

      <Field label="Gender">
        <select
          value={form.gender}
          onChange={(e) => set({ gender: e.target.value })}
          className="border border-border px-3 py-2 bg-background text-sm outline-none w-full"
        >
          <option value="">Select gender…</option>
          <option value="women">Women</option>
          <option value="men">Men</option>
          <option value="unisex">Unisex</option>
          <option value="kids">Kids</option>
        </select>
      </Field>

      <div className="grid grid-cols-2 gap-4">
        <ToggleSwitch
          checked={form.requires_shipping}
          onChange={(v) => set({ requires_shipping: v })}
          label="Requires shipping"
        />
        <ToggleSwitch
          checked={form.is_customizable}
          onChange={(v) => set({ is_customizable: v })}
          label="Customizable"
        />
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          Dimensions (cm)
        </p>
        <div className="grid grid-cols-3 gap-3">
          <TextInput
            type="number"
            value={form.length_cm}
            onChange={(v) => set({ length_cm: v })}
            placeholder="L"
          />
          <TextInput
            type="number"
            value={form.width_cm}
            onChange={(v) => set({ width_cm: v })}
            placeholder="W"
          />
          <TextInput
            type="number"
            value={form.height_cm}
            onChange={(v) => set({ height_cm: v })}
            placeholder="H"
          />
        </div>
      </div>
    </div>
  );
}

// ─── Media Section ────────────────────────────────────────────────────────────

function MediaSection({
  productId,
  pendingImages,
  savedImages,
  onAddPending,
  onRemovePending,
  onSetPrimaryPending,
  onDeleteSaved,
  onSetPrimarySaved,
  onEditCropPending,
  onEditCropSaved,
  onReplaceSaved,
  onMoveSaved,
  busyImageIds,
  generatingImageIds,
  error,
}: {
  productId?: string;
  pendingImages: PendingImage[];
  savedImages: ProductImage[];
  onAddPending: (files: File[]) => void;
  onRemovePending: (id: string) => void;
  onSetPrimaryPending: (id: string) => void;
  onDeleteSaved: (id: string) => void;
  onSetPrimarySaved: (id: string) => void;
  onEditCropPending: (id: string) => void;
  onEditCropSaved: (id: string) => void;
  onReplaceSaved: (id: string, file: File) => void;
  onMoveSaved: (id: string, direction: "up" | "down") => void;
  busyImageIds: Set<string>;
  generatingImageIds: Set<string>;
  error?: string;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const replaceFileRef = useRef<HTMLInputElement>(null);
  const replaceTargetRef = useRef<string | null>(null);
  const [dragging, setDragging] = useState(false);
  // Files rejected by the client-side resolution pre-check — shown inline,
  // right where they were dropped/picked, instead of only surfacing as a
  // 422 after a wasted upload round-trip (mirrors validation.py's message
  // exactly via validateFileResolution).
  const [rejectedFiles, setRejectedFiles] = useState<{ id: string; message: string }[]>([]);

  const validateAndAddPending = useCallback(
    async (files: File[]) => {
      // Each new add attempt starts clean — a rejection from a previous,
      // unrelated drop shouldn't keep showing once the admin has moved on.
      setRejectedFiles([]);
      const valid: File[] = [];
      const rejected: { id: string; message: string }[] = [];
      for (const file of files) {
        const problem = await validateFileResolution(file, PRODUCT_PRESET);
        if (problem) {
          rejected.push({ id: uid(), message: `${file.name}: ${problem}` });
        } else {
          valid.push(file);
        }
      }
      if (rejected.length) setRejectedFiles(rejected);
      if (valid.length) onAddPending(valid);
    },
    [onAddPending],
  );

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
    if (files.length) void validateAndAddPending(files);
  };

  const handleFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length) void validateAndAddPending(files);
  };

  const triggerReplace = (imageId: string) => {
    replaceTargetRef.current = imageId;
    replaceFileRef.current?.click();
  };

  const handleReplaceFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const targetId = replaceTargetRef.current;
    e.target.value = "";
    replaceTargetRef.current = null;
    if (!file || !targetId) return;
    // Same reasoning as validateAndAddPending: this attempt's outcome
    // replaces whatever was left over from a previous, unrelated one.
    setRejectedFiles([]);
    const problem = await validateFileResolution(file, PRODUCT_PRESET);
    if (problem) {
      setRejectedFiles([{ id: uid(), message: `${file.name}: ${problem}` }]);
      return;
    }
    onReplaceSaved(targetId, file);
  };

  const totalCount = savedImages.length + pendingImages.length;

  return (
    <div className="flex flex-col gap-4 pt-5">
      {error && (
        <p className="text-[11px] text-destructive flex items-center gap-1">
          <AlertCircle className="size-3" />
          {error}
        </p>
      )}
      {rejectedFiles.map((r) => (
        <div
          key={r.id}
          className="flex items-start gap-2 rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
          <span className="flex-1">{r.message}</span>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => setRejectedFiles((prev) => prev.filter((x) => x.id !== r.id))}
            className="shrink-0 opacity-70 hover:opacity-100"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}

      <div
        className={`border-2 border-dashed rounded-none p-8 text-center transition-colors cursor-pointer ${
          dragging
            ? "border-primary bg-primary/5"
            : "border-border hover:border-muted-foreground/50"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
      >
        <Upload className="size-8 mx-auto text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">
          Drag & drop images or <span className="text-foreground underline">browse</span>
        </p>
        <p className="text-[11px] text-muted-foreground mt-1">JPG, PNG, WebP · max 10 MB each</p>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          onChange={handleFiles}
          className="hidden"
        />
      </div>

      {/* Shared hidden input for "Replace" — target image id tracked in a ref
          so a single input can serve every saved thumbnail. */}
      <input
        ref={replaceFileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleReplaceFile}
        className="hidden"
      />

      {totalCount > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {savedImages.map((img, i) => {
            const busy = busyImageIds.has(img.id);
            const generating = generatingImageIds.has(img.id);
            return (
              <div
                key={img.id}
                className="relative group border border-border aspect-square overflow-hidden bg-secondary"
              >
                <img
                  src={img.thumbnail_url ?? img.url}
                  alt={img.alt_text ?? ""}
                  className="w-full h-full object-cover"
                />
                {generating && (
                  <div className="absolute bottom-1 right-1 flex items-center gap-1 bg-background/90 text-foreground text-[9px] px-1.5 py-0.5 rounded-sm shadow-sm">
                    <RefreshCw className="size-2.5 animate-spin" />
                    Generating…
                  </div>
                )}
                {img.is_primary && (
                  <span className="absolute top-1 left-1 bg-primary text-primary-foreground text-[9px] uppercase tracking-wider px-1.5 py-0.5">
                    Primary
                  </span>
                )}
                {img.crop_x != null && (
                  <span className="absolute top-1 right-1 bg-background/90 text-foreground text-[9px] uppercase tracking-wider px-1.5 py-0.5">
                    Cropped
                  </span>
                )}
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                  {i > 0 && (
                    <button
                      type="button"
                      onClick={() => onMoveSaved(img.id, "up")}
                      disabled={busy}
                      className="bg-background/90 p-1.5 rounded-sm disabled:opacity-50"
                      title="Move earlier"
                    >
                      {busy ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <ChevronUp className="size-3.5" />
                      )}
                    </button>
                  )}
                  {i < savedImages.length - 1 && (
                    <button
                      type="button"
                      onClick={() => onMoveSaved(img.id, "down")}
                      disabled={busy}
                      className="bg-background/90 p-1.5 rounded-sm disabled:opacity-50"
                      title="Move later"
                    >
                      {busy ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <ChevronDown className="size-3.5" />
                      )}
                    </button>
                  )}
                  {!img.is_primary && (
                    <button
                      type="button"
                      onClick={() => onSetPrimarySaved(img.id)}
                      disabled={busy}
                      className="bg-background/90 p-1.5 rounded-sm disabled:opacity-50"
                      title="Set as primary"
                    >
                      {busy ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <Star className="size-3.5" />
                      )}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => onEditCropSaved(img.id)}
                    disabled={busy}
                    className="bg-background/90 p-1.5 rounded-sm disabled:opacity-50"
                    title="Edit crop"
                  >
                    {busy ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <CropIcon className="size-3.5" />
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => triggerReplace(img.id)}
                    disabled={busy}
                    className="bg-background/90 p-1.5 rounded-sm disabled:opacity-50"
                    title="Replace image"
                  >
                    {busy ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <ImagePlus className="size-3.5" />
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm("Delete this image?")) onDeleteSaved(img.id);
                    }}
                    disabled={busy}
                    className="bg-destructive/90 text-destructive-foreground p-1.5 rounded-sm disabled:opacity-50"
                    title="Delete"
                  >
                    {busy ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="size-3.5" />
                    )}
                  </button>
                </div>
              </div>
            );
          })}

          {pendingImages.map((img, i) => (
            <div
              key={img.id}
              className="relative group border border-dashed border-border aspect-square overflow-hidden bg-secondary"
            >
              <img src={img.preview} alt="" className="w-full h-full object-cover" />
              <div className="absolute top-1 right-1 bg-amber-500/90 text-white text-[9px] uppercase tracking-wider px-1.5 py-0.5">
                Pending
              </div>
              {img.crop && (
                <span className="absolute top-1 right-16 bg-background/90 text-foreground text-[9px] uppercase tracking-wider px-1.5 py-0.5">
                  Cropped
                </span>
              )}
              {savedImages.length === 0 && i === 0 && (
                <span className="absolute top-1 left-1 bg-primary text-primary-foreground text-[9px] uppercase tracking-wider px-1.5 py-0.5">
                  Primary
                </span>
              )}
              <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                <button
                  type="button"
                  onClick={() => onEditCropPending(img.id)}
                  className="bg-background/90 p-1.5 rounded-sm"
                  title="Edit crop"
                >
                  <CropIcon className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onRemovePending(img.id)}
                  className="bg-destructive/90 text-destructive-foreground p-1.5 rounded-sm"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {totalCount === 0 && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ImageIcon className="size-3.5" />
          No images yet
        </div>
      )}
    </div>
  );
}

// ─── Variants Section ─────────────────────────────────────────────────────────

function VariantsSection({
  form,
  set,
  baseSku,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
  baseSku: string;
}) {
  const addOption = () => {
    set({
      variant_options: [...form.variant_options, { id: uid(), name: "", values: [], newValue: "" }],
    });
  };

  const removeOption = (id: string) => {
    set({ variant_options: form.variant_options.filter((o) => o.id !== id) });
  };

  const updateOption = (id: string, patch: Partial<VariantOption>) => {
    set({
      variant_options: form.variant_options.map((o) => (o.id === id ? { ...o, ...patch } : o)),
    });
  };

  const addValue = (optionId: string) => {
    const opt = form.variant_options.find((o) => o.id === optionId);
    if (!opt || !opt.newValue.trim()) return;
    const val = opt.newValue.trim();
    if (!opt.values.includes(val)) {
      updateOption(optionId, { values: [...opt.values, val], newValue: "" });
    }
  };

  const removeValue = (optionId: string, val: string) => {
    const opt = form.variant_options.find((o) => o.id === optionId);
    if (!opt) return;
    updateOption(optionId, { values: opt.values.filter((v) => v !== val) });
  };

  const generateVariants = () => {
    const optionsWithValues = form.variant_options.filter(
      (o) => o.name.trim() && o.values.length > 0,
    );
    if (optionsWithValues.length === 0) return;
    const valueSets = optionsWithValues.map((o) => o.values);
    const combos = cartesian(valueSets);
    const newVariants: LocalVariant[] = combos.map((combo, i) => {
      const name = combo.join(" / ");
      const suffix = combo.map((v) => v.slice(0, 3).toUpperCase()).join("-");
      return {
        id: uid(),
        sku: `${baseSku || "HDH"}-${suffix}`,
        name,
        price_adjustment: 0,
        stock_quantity: 0,
        weight_grams: null,
        is_active: true,
      };
    });
    set({ variants: newVariants });
  };

  const updateVariant = (id: string, patch: Partial<LocalVariant>) => {
    set({
      variants: form.variants.map((v) => (v.id === id ? { ...v, ...patch } : v)),
    });
  };

  const removeVariant = (id: string) => {
    set({ variants: form.variants.filter((v) => v.id !== id) });
  };

  const addManualVariant = () => {
    set({
      variants: [
        ...form.variants,
        {
          id: uid(),
          sku: `${baseSku || "HDH"}-V${form.variants.length + 1}`,
          name: `Variant ${form.variants.length + 1}`,
          price_adjustment: 0,
          stock_quantity: 0,
          weight_grams: null,
          is_active: true,
        },
      ],
    });
  };

  return (
    <div className="flex flex-col gap-5 pt-5">
      <ToggleSwitch
        checked={form.enable_variants}
        onChange={(v) => set({ enable_variants: v })}
        label="Enable product variants"
      />

      {form.enable_variants && (
        <>
          <div className="flex flex-col gap-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Option Types
            </p>
            {form.variant_options.map((opt) => (
              <div key={opt.id} className="border border-border p-4 flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <TextInput
                    value={opt.name}
                    onChange={(v) => updateOption(opt.id, { name: v })}
                    placeholder="Option name (e.g. Size, Color)"
                    className="flex-1"
                  />
                  <button
                    type="button"
                    onClick={() => removeOption(opt.id)}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <X className="size-4" />
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {opt.values.map((val) => (
                    <span
                      key={val}
                      className="inline-flex items-center gap-1 border border-border px-2 py-0.5 text-xs"
                    >
                      {val}
                      <button
                        type="button"
                        onClick={() => removeValue(opt.id, val)}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <TextInput
                    value={opt.newValue}
                    onChange={(v) => updateOption(opt.id, { newValue: v })}
                    placeholder="Add value (e.g. 16, 18)"
                    className="flex-1"
                  />
                  <button
                    type="button"
                    onClick={() => addValue(opt.id)}
                    className="shrink-0 border border-border px-3 text-sm hover:bg-secondary"
                    onKeyDown={(e) => e.key === "Enter" && addValue(opt.id)}
                  >
                    Add
                  </button>
                </div>
              </div>
            ))}
            <div className="flex gap-3">
              <button
                type="button"
                onClick={addOption}
                className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                <Plus className="size-3.5" /> Add Option
              </button>
              {form.variant_options.length > 0 && (
                <button
                  type="button"
                  onClick={generateVariants}
                  className="text-[11px] uppercase tracking-[0.18em] bg-primary text-primary-foreground px-4 py-2 hover:opacity-90"
                >
                  Generate Combinations
                </button>
              )}
            </div>
          </div>

          {form.variants.length > 0 && (
            <div className="border border-border overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary text-[11px] uppercase tracking-[0.15em] text-muted-foreground text-left">
                  <tr>
                    <th className="px-3 py-2">Variant</th>
                    <th className="px-3 py-2">SKU</th>
                    <th className="px-3 py-2">Price Adj (₹)</th>
                    <th className="px-3 py-2">Stock</th>
                    <th className="px-3 py-2">Active</th>
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {form.variants.map((v) => (
                    <tr key={v.id}>
                      <td className="px-3 py-2">
                        <input
                          value={v.name}
                          onChange={(e) => updateVariant(v.id, { name: e.target.value })}
                          className="border border-border px-2 py-1 bg-transparent text-sm outline-none w-full min-w-[100px]"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={v.sku}
                          onChange={(e) => updateVariant(v.id, { sku: e.target.value })}
                          className="border border-border px-2 py-1 bg-transparent text-sm outline-none font-mono w-full min-w-[120px]"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="number"
                          value={v.price_adjustment}
                          onChange={(e) =>
                            updateVariant(v.id, {
                              price_adjustment: parseFloat(e.target.value) || 0,
                            })
                          }
                          className="border border-border px-2 py-1 bg-transparent text-sm outline-none w-24"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="number"
                          value={v.stock_quantity}
                          onChange={(e) =>
                            updateVariant(v.id, { stock_quantity: parseInt(e.target.value) || 0 })
                          }
                          className="border border-border px-2 py-1 bg-transparent text-sm outline-none w-20"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={v.is_active}
                          onChange={(e) => updateVariant(v.id, { is_active: e.target.checked })}
                          className="accent-primary size-4"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => removeVariant(v.id)}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <button
            type="button"
            onClick={addManualVariant}
            className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground flex items-center gap-1"
          >
            <Plus className="size-3.5" /> Add Variant Manually
          </button>
        </>
      )}
    </div>
  );
}

// ─── Attributes Section ───────────────────────────────────────────────────────

function AttributesSection({
  form,
  set,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
}) {
  const addAttr = () => {
    set({
      attributes: [...form.attributes, { id: uid(), name: "", value: "" }],
    });
  };

  const updateAttr = (id: string, patch: Partial<LocalAttribute>) => {
    set({
      attributes: form.attributes.map((a) => (a.id === id ? { ...a, ...patch } : a)),
    });
  };

  const removeAttr = (id: string) => {
    set({ attributes: form.attributes.filter((a) => a.id !== id) });
  };

  const SUGGESTIONS = [
    "Stone",
    "Finish",
    "Occasion",
    "Style",
    "Warranty",
    "Material",
    "Closure",
    "Chain Length",
    "Setting",
    "Plating",
  ];

  return (
    <div className="flex flex-col gap-4 pt-5">
      {form.attributes.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Add custom attributes to describe the product in detail.
        </p>
      )}

      <div className="flex flex-col gap-2">
        {form.attributes.map((attr, i) => (
          <div key={attr.id} className="flex gap-2 items-center">
            <input
              value={attr.name}
              onChange={(e) => updateAttr(attr.id, { name: e.target.value })}
              placeholder="Name (e.g. Stone)"
              list="attr-suggestions"
              className="border border-border px-3 py-2 bg-transparent text-sm outline-none flex-1"
            />
            <input
              value={attr.value}
              onChange={(e) => updateAttr(attr.id, { value: e.target.value })}
              placeholder="Value (e.g. CZ)"
              className="border border-border px-3 py-2 bg-transparent text-sm outline-none flex-1"
            />
            <button
              type="button"
              onClick={() => removeAttr(attr.id)}
              className="text-muted-foreground hover:text-destructive shrink-0"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        ))}
        <datalist id="attr-suggestions">
          {SUGGESTIONS.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>

      <button
        type="button"
        onClick={addAttr}
        className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground flex items-center gap-1 self-start"
      >
        <Plus className="size-3.5" /> Add Attribute
      </button>

      {form.attributes.length > 0 && (
        <div className="bg-secondary/30 border border-border p-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground mb-2">
            Preview
          </p>
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            {form.attributes
              .filter((a) => a.name && a.value)
              .map((a) => (
                <div key={a.id} className="text-sm">
                  <span className="text-muted-foreground">{a.name}: </span>
                  <span>{a.value}</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── SEO Section ──────────────────────────────────────────────────────────────

interface SeoEdited {
  title: boolean;
  desc: boolean;
  kw: boolean;
}

function SeoCharCounter({
  count,
  min,
  max,
  warnLow,
  warnHigh,
}: {
  count: number;
  min: number;
  max: number;
  warnLow: number;
  warnHigh: number;
}) {
  const color =
    count >= min && count <= max
      ? "text-emerald-600"
      : (count >= warnLow && count < min) || (count > max && count <= warnHigh)
        ? "text-amber-500"
        : "text-destructive";
  return (
    <span className={`text-[11px] tabular-nums font-mono ${color}`}>
      {count} / {max}
    </span>
  );
}

function SeoBadge({ edited }: { edited: boolean }) {
  return (
    <span
      className={`text-[9px] uppercase tracking-[0.15em] px-1.5 py-0.5 font-medium border ${
        edited
          ? "bg-secondary text-muted-foreground border-border"
          : "bg-primary/10 text-primary border-primary/20"
      }`}
    >
      {edited ? "Custom" : "Auto Generated"}
    </span>
  );
}

function SeoFieldHeader({
  label,
  edited,
  onRegenerate,
  counter,
}: {
  label: string;
  edited: boolean;
  onRegenerate: () => void;
  counter?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2 flex-wrap">
      <label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <SeoBadge edited={edited} />
        {counter}
        <button
          type="button"
          onClick={onRegenerate}
          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary transition-colors"
        >
          <Sparkles className="size-3" />
          Regenerate
        </button>
      </div>
    </div>
  );
}

function SeoSection({
  form,
  set,
  mode,
  categoryName,
  collectionNames,
  seoEdited,
  onSetSeoEdited,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
  mode: "new" | "edit";
  categoryName: string;
  collectionNames: string[];
  seoEdited: SeoEdited;
  onSetSeoEdited: (patch: Partial<SeoEdited>) => void;
}) {
  const previewTitle = form.meta_title || form.name || "Product Title";
  const previewDesc = form.meta_description || form.short_description || "Product description…";

  const regenTitle = () => {
    set({ meta_title: generateMetaTitle(form.name, form.metal_type, form.purity) });
    onSetSeoEdited({ title: false });
  };

  const regenDesc = () => {
    set({
      meta_description: generateMetaDescription(
        form.short_description,
        form.description,
        form.name,
        categoryName,
        form.metal_type,
      ),
    });
    onSetSeoEdited({ desc: false });
  };

  const regenKw = () => {
    set({
      meta_keywords: generateMetaKeywords(
        form.name,
        categoryName,
        collectionNames,
        form.gender,
        form.metal_type,
        form.purity,
      ),
    });
    onSetSeoEdited({ kw: false });
  };

  const regenAll = () => {
    set({
      meta_title: generateMetaTitle(form.name, form.metal_type, form.purity),
      meta_description: generateMetaDescription(
        form.short_description,
        form.description,
        form.name,
        categoryName,
        form.metal_type,
      ),
      meta_keywords: generateMetaKeywords(
        form.name,
        categoryName,
        collectionNames,
        form.gender,
        form.metal_type,
        form.purity,
      ),
    });
    onSetSeoEdited({ title: false, desc: false, kw: false });
  };

  const kwCount = form.meta_keywords
    ? form.meta_keywords.split(",").filter((k) => k.trim()).length
    : 0;

  return (
    <div className="flex flex-col gap-5 pt-5">
      {/* Header row with Regenerate All */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Auto-generated from product details. Edit any field to customise.
        </p>
        <button
          type="button"
          onClick={regenAll}
          className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.18em] text-primary hover:opacity-75 transition-opacity shrink-0"
        >
          <Sparkles className="size-3.5" />
          Regenerate All
        </button>
      </div>

      {/* Meta Title */}
      <div className="flex flex-col gap-1.5">
        <SeoFieldHeader
          label="Meta Title"
          edited={seoEdited.title}
          onRegenerate={regenTitle}
          counter={
            <SeoCharCounter
              count={form.meta_title.length}
              min={40}
              max={60}
              warnLow={30}
              warnHigh={70}
            />
          }
        />
        <TextInput
          value={form.meta_title}
          onChange={(v) => {
            set({ meta_title: v });
            onSetSeoEdited({ title: true });
          }}
          placeholder="Automatically generated from the product name."
        />
      </div>

      {/* Meta Description */}
      <div className="flex flex-col gap-1.5">
        <SeoFieldHeader
          label="Meta Description"
          edited={seoEdited.desc}
          onRegenerate={regenDesc}
          counter={
            <SeoCharCounter
              count={form.meta_description.length}
              min={120}
              max={160}
              warnLow={100}
              warnHigh={180}
            />
          }
        />
        <textarea
          value={form.meta_description}
          onChange={(e) => {
            set({ meta_description: e.target.value });
            onSetSeoEdited({ desc: true });
          }}
          rows={3}
          placeholder="Automatically generated from the short description."
          className="border border-border px-3 py-2 bg-transparent text-sm outline-none w-full resize-none"
        />
      </div>

      {/* Meta Keywords */}
      <div className="flex flex-col gap-1.5">
        <SeoFieldHeader label="Meta Keywords" edited={seoEdited.kw} onRegenerate={regenKw} />
        <TextInput
          value={form.meta_keywords}
          onChange={(v) => {
            set({ meta_keywords: v });
            onSetSeoEdited({ kw: true });
          }}
          placeholder="Automatically generated from the product details."
        />
        {kwCount > 0 && (
          <p className="text-[11px] text-muted-foreground">
            {kwCount} keyword{kwCount !== 1 ? "s" : ""} · comma-separated
          </p>
        )}
      </div>

      {/* Google Search Preview */}
      <div className="border border-border p-4 bg-white text-black">
        <p className="text-[11px] uppercase tracking-wider text-gray-400 mb-2">
          Google Search Preview
        </p>
        <p className="text-[13px] text-green-700 truncate mb-0.5">
          hadha.co &rsaquo; products &rsaquo; {form.slug || "product-slug"}
        </p>
        <p className="text-blue-700 text-[18px] font-medium leading-snug truncate">
          {previewTitle}
        </p>
        <p className="text-gray-600 text-sm mt-0.5 line-clamp-2 leading-relaxed">{previewDesc}</p>
      </div>
    </div>
  );
}

// ─── Publish Sidebar ──────────────────────────────────────────────────────────

function PublishSidebar({
  form,
  set,
  mode,
  saving,
  onSaveDraft,
  onPublish,
  onCancel,
  isDirty,
  pendingImagesCount,
  savedImagesCount,
  collectionsCount,
  variantsCount,
  selectedCategory,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
  mode: "new" | "edit";
  saving: boolean;
  onSaveDraft: () => void;
  onPublish: () => void;
  onCancel: () => void;
  isDirty: boolean;
  pendingImagesCount: number;
  savedImagesCount: number;
  collectionsCount: number;
  variantsCount: number;
  selectedCategory: string;
}) {
  const totalImages = pendingImagesCount + savedImagesCount;

  return (
    <div className="flex flex-col gap-4">
      {isDirty && (
        <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 border border-amber-200 px-3 py-2">
          <AlertCircle className="size-3.5 shrink-0" />
          Unsaved changes
        </div>
      )}

      <div className="border border-border bg-background p-4 flex flex-col gap-4">
        <p className="text-[11px] uppercase tracking-[0.22em] font-medium">Status</p>
        <div className="flex flex-col gap-2">
          {(["draft", "active", "archived"] as const).map((s) => (
            <label key={s} className="flex items-center gap-2.5 cursor-pointer">
              <input
                type="radio"
                name="status"
                value={s}
                checked={form.status === s}
                onChange={() => set({ status: s })}
                className="accent-primary"
              />
              <span className="text-sm capitalize">{s}</span>
              {s === "active" && (
                <span className="ml-auto text-[10px] bg-accent/15 text-accent px-2 py-0.5 uppercase tracking-wider">
                  Live
                </span>
              )}
            </label>
          ))}
        </div>
      </div>

      <div className="border border-border bg-background p-4 flex flex-col gap-3">
        <p className="text-[11px] uppercase tracking-[0.22em] font-medium">Summary</p>
        <div className="flex flex-col gap-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Images</span>
            <span className={totalImages === 0 ? "text-destructive" : ""}>{totalImages}</span>
          </div>
          {pendingImagesCount > 0 && (
            <div className="flex justify-between">
              <span className="text-muted-foreground text-xs">Pending upload</span>
              <span className="text-xs text-amber-600">{pendingImagesCount}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-muted-foreground">Variants</span>
            <span>{variantsCount || (form.enable_variants ? 0 : "—")}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Collections</span>
            <span>{collectionsCount}</span>
          </div>
          {selectedCategory && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Category</span>
              <span className="text-right max-w-[120px] truncate text-xs">{selectedCategory}</span>
            </div>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={onPublish}
        disabled={saving}
        className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3 disabled:opacity-50 hover:opacity-90 transition-opacity"
      >
        {saving && <Loader2 className="size-3.5 animate-spin" />}
        {saving ? "Saving…" : mode === "new" ? "Publish Product" : "Save & Publish"}
      </button>

      <button
        type="button"
        onClick={onSaveDraft}
        disabled={saving}
        className="w-full flex items-center justify-center gap-2 border border-border text-[11px] uppercase tracking-[0.22em] py-3 disabled:opacity-50 hover:bg-secondary"
      >
        {saving && <Loader2 className="size-3.5 animate-spin" />}
        {saving ? "Saving…" : "Save Draft"}
      </button>

      <button
        type="button"
        onClick={onCancel}
        disabled={saving}
        className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground text-center"
      >
        Cancel
      </button>
    </div>
  );
}

// ─── Main ProductForm ─────────────────────────────────────────────────────────

export interface ProductFormProps {
  mode: "new" | "edit";
  initialProduct?: ProductDetail;
  initialCollectionIds?: string[];
}

export function ProductForm({ mode, initialProduct, initialCollectionIds }: ProductFormProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // ── Data loading ────────────────────────────────────────────────────────────

  const { data: categoryTree = [] } = useQuery({
    queryKey: queryKeys.categories.tree,
    queryFn: () => api.get<CategoryTreeNode[]>("/categories"),
    staleTime: 300_000,
  });

  const { data: collectionsResponse } = useQuery({
    queryKey: queryKeys.admin.collectionsList({ page_size: 200 }),
    queryFn: () =>
      api.get<CollectionListResponse>("/admin/collections", {
        params: { page_size: 200 },
      }),
    staleTime: 300_000,
  });
  const collections: CollectionListItem[] = collectionsResponse?.items ?? [];

  // ── Local state ─────────────────────────────────────────────────────────────

  const [categoryTreeLocal, setCategoryTreeLocal] = useState<CategoryTreeNode[]>([]);
  const [collectionsLocal, setCollectionsLocal] = useState<CollectionListItem[]>([]);

  useEffect(() => {
    if (categoryTree.length) setCategoryTreeLocal(categoryTree);
  }, [categoryTree]);

  useEffect(() => {
    if (collections.length) setCollectionsLocal(collections);
  }, [collections]);

  const initialForm = useCallback((): FormState => {
    if (initialProduct) {
      const f = productToForm(
        initialProduct,
        categoryTreeLocal.length ? categoryTreeLocal : categoryTree,
      );
      if (initialCollectionIds) f.collection_ids = initialCollectionIds;
      return f;
    }
    return emptyForm();
  }, [initialProduct, initialCollectionIds, categoryTree, categoryTreeLocal]);

  const [form, setFormRaw] = useState<FormState>(initialForm);
  const [savedImages, setSavedImages] = useState<ProductImage[]>(initialProduct?.images ?? []);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [saving, setSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [deletedVariantIds, setDeletedVariantIds] = useState<string[]>([]);
  const [deletedAttributeNames, setDeletedAttributeNames] = useState<string[]>([]);
  const initialCollectionIdsRef = useRef<string[]>(initialCollectionIds ?? []);

  // SEO override flags — true means the admin edited that field manually
  const [seoEdited, setSeoEdited] = useState<SeoEdited>({
    title: mode === "edit",
    desc: mode === "edit",
    kw: mode === "edit",
  });

  const updateSeoEdited = useCallback((patch: Partial<SeoEdited>) => {
    setSeoEdited((prev) => ({ ...prev, ...patch }));
  }, []);

  // Keep a ref to description so auto-gen effects don't need it as a dep
  const descriptionRef = useRef(form.description);
  useEffect(() => {
    descriptionRef.current = form.description;
  }, [form.description]);

  // Sync when initialProduct data becomes available (edit mode with loading)
  useEffect(() => {
    if (initialProduct && categoryTree.length) {
      const f = productToForm(initialProduct, categoryTree);
      if (initialCollectionIds) f.collection_ids = initialCollectionIds;
      setFormRaw(f);
      setSavedImages(initialProduct.images);
      setDeletedVariantIds([]);
      setDeletedAttributeNames([]);
      setIsDirty(false);
    }
  }, [initialProduct?.id, initialCollectionIds?.join(","), categoryTree.length]);

  const set = useCallback((patch: Partial<FormState>) => {
    setFormRaw((prev) => ({ ...prev, ...patch }));
    setIsDirty(true);
  }, []);

  // ── SKU generation ──────────────────────────────────────────────────────────

  const [skuLoading, setSkuLoading] = useState(false);

  const generateSku = useCallback(async () => {
    setSkuLoading(true);
    try {
      const parentName =
        categoryTreeLocal.find((c) => c.id === form.parent_category_id)?.name ?? "XX";
      const prefix = getCategoryPrefix(parentName);
      const result = await api.get<{ sku: string }>("/admin/products/generate-sku", {
        params: { prefix },
      });
      set({ sku: result.sku });
    } catch (e) {
      toast.error("Could not generate SKU");
    } finally {
      setSkuLoading(false);
    }
  }, [form.parent_category_id, categoryTreeLocal, set]);

  // Auto-generate SKU when parent category is first selected
  const prevParentRef = useRef("");
  useEffect(() => {
    if (
      form.parent_category_id &&
      form.parent_category_id !== prevParentRef.current &&
      !form.sku &&
      mode === "new"
    ) {
      prevParentRef.current = form.parent_category_id;
      generateSku();
    }
  }, [form.parent_category_id, form.sku, mode]);

  // ── Auto-generate SEO (create mode only, respects manual-edit flags) ─────────

  useEffect(() => {
    if (mode === "edit" || seoEdited.title) return;
    const v = generateMetaTitle(form.name, form.metal_type, form.purity);
    if (v) set({ meta_title: v });
  }, [form.name, form.metal_type, form.purity, seoEdited.title, mode]);

  useEffect(() => {
    if (mode === "edit" || seoEdited.desc) return;
    const catName =
      categoryTreeLocal.flatMap((p) => p.children).find((c) => c.id === form.category_id)?.name ??
      "";
    const v = generateMetaDescription(
      form.short_description,
      descriptionRef.current,
      form.name,
      catName,
      form.metal_type,
    );
    if (v) set({ meta_description: v });
  }, [
    form.name,
    form.short_description,
    form.category_id,
    form.metal_type,
    seoEdited.desc,
    mode,
    categoryTreeLocal,
  ]);

  useEffect(() => {
    if (mode === "edit" || seoEdited.kw) return;
    const catName =
      categoryTreeLocal.flatMap((p) => p.children).find((c) => c.id === form.category_id)?.name ??
      "";
    const colNames = (collectionsLocal.length ? collectionsLocal : collections)
      .filter((c) => form.collection_ids.includes(c.id))
      .map((c) => c.name);
    const v = generateMetaKeywords(
      form.name,
      catName,
      colNames,
      form.gender,
      form.metal_type,
      form.purity,
    );
    if (v) set({ meta_keywords: v });
  }, [
    form.name,
    form.category_id,
    form.collection_ids,
    form.gender,
    form.metal_type,
    form.purity,
    seoEdited.kw,
    mode,
    categoryTreeLocal,
    collectionsLocal,
  ]);

  // ── Image handlers ──────────────────────────────────────────────────────────

  // Crop editor queue — each newly-uploaded image gets its own turn, in
  // order, so cropping image 1 of 4 never touches images 2-4's state. "Edit
  // Crop" / "Replace" on an existing image just append a single-item turn.
  const [cropQueue, setCropQueue] = useState<CropTarget[]>([]);
  const [cropSaving, setCropSaving] = useState(false);
  const activeCropTarget = cropQueue[0] ?? null;

  // Re-editing a *saved* image must operate on the untouched original plus
  // its previously-saved crop geometry for every breakpoint, not the
  // desktop-only fields cached on `ProductImage` — so each time the queue's
  // active target becomes a saved image, its true current state is fetched
  // fresh via `getImage` (mirrors Collection/Category; see docs audit
  // CB-2/HP-6). `id` guards against a stale response landing after the
  // queue has already moved on to a different image.
  const [savedCropFetch, setSavedCropFetch] = useState<{
    id: string;
    originalUrl: string;
    initialCrops: Partial<Record<Breakpoint, BreakpointCropGeometry>> | undefined;
    altText: string | null;
  } | null>(null);
  const [savedCropFetchLoading, setSavedCropFetchLoading] = useState(false);

  useEffect(() => {
    if (!activeCropTarget || activeCropTarget.kind !== "saved") {
      setSavedCropFetch(null);
      setSavedCropFetchLoading(false);
      return;
    }
    const id = activeCropTarget.id;
    let cancelled = false;
    setSavedCropFetchLoading(true);
    getImage(id)
      .then((raw) => {
        if (cancelled) return;
        setSavedCropFetch({
          id,
          originalUrl: raw.original_url,
          initialCrops: parseStoredCrops(raw),
          altText: raw.alt_text,
        });
      })
      .catch((e) => {
        if (cancelled) return;
        toast.error(toUserMessage(e as Error));
        setCropQueue((prev) => prev.filter((t) => !(t.kind === "saved" && t.id === id)));
      })
      .finally(() => {
        if (!cancelled) setSavedCropFetchLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCropTarget]);

  const enqueueCrop = useCallback((target: CropTarget) => {
    setCropQueue((prev) => [...prev, target]);
  }, []);

  const dequeueCrop = useCallback(() => {
    setCropQueue((prev) => prev.slice(1));
  }, []);

  // Per-saved-image operation lock — delete/replace/set-primary/crop on a
  // given saved image id must never overlap, or a slow request (e.g. replace)
  // can lose a race against a fast one (e.g. delete) on the same row and
  // leave the gallery pointing at a soft-deleted/stale image. The ref backs
  // synchronous check-and-set (state updates land a render late, which is
  // enough time for a second click to slip through); the state mirror drives
  // the disabled UI.
  const busyImageIdsRef = useRef<Set<string>>(new Set());
  const [busyImageIds, setBusyImageIds] = useState<Set<string>>(new Set());

  const tryBeginImageOp = useCallback((imageId: string): boolean => {
    if (busyImageIdsRef.current.has(imageId)) return false;
    busyImageIdsRef.current.add(imageId);
    setBusyImageIds(new Set(busyImageIdsRef.current));
    return true;
  }, []);

  const endImageOp = useCallback((imageId: string) => {
    busyImageIdsRef.current.delete(imageId);
    setBusyImageIds(new Set(busyImageIdsRef.current));
  }, []);

  // Separate from busyImageIds: an image can be "done" (unlocked, editor
  // closed) while its variants are still generating in the background
  // (docs audit CB-1 Phase 2) — this only drives the "Generating…" badge,
  // never the disabled/locked UI busyImageIds controls.
  const [generatingImageIds, setGeneratingImageIds] = useState<Set<string>>(new Set());

  // Fire-and-forget: waits for the background worker to actually finish
  // generating variants for one saved image, then swaps in the real
  // thumbnail. Never blocks the crop/replace flow that called it.
  const awaitGeneration = useCallback(
    (imageId: string) => {
      setGeneratingImageIds((prev) => new Set(prev).add(imageId));
      pollImageUntilReady(imageId)
        .then((fresh) => {
          const updated = mapImageOutToProductImage(fresh);
          // Belt-and-suspenders against any intermediate cache (CDN, proxy)
          // that might still serve bytes cached under an earlier `?v=`
          // during the pending->ready window — see bustCacheUrl.
          updated.url = updated.url ? bustCacheUrl(updated.url) : updated.url;
          updated.thumbnail_url = updated.thumbnail_url
            ? bustCacheUrl(updated.thumbnail_url)
            : updated.thumbnail_url;
          updated.medium_url = updated.medium_url
            ? bustCacheUrl(updated.medium_url)
            : updated.medium_url;
          updated.large_url = updated.large_url
            ? bustCacheUrl(updated.large_url)
            : updated.large_url;
          setSavedImages((prev) => prev.map((i) => (i.id === imageId ? updated : i)));
          if (initialProduct) {
            queryClient.invalidateQueries({ queryKey: queryKeys.admin.product(initialProduct.id) });
            queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
          }
        })
        .catch((e) => {
          toast.error(toUserMessage(e as Error) || "Image processing failed — try again.");
        })
        .finally(() => {
          setGeneratingImageIds((prev) => {
            const next = new Set(prev);
            next.delete(imageId);
            return next;
          });
        });
    },
    [initialProduct, queryClient],
  );

  const handleAltTextCommit = useCallback(
    async (value: string) => {
      if (!activeCropTarget || activeCropTarget.kind !== "saved") return;
      const targetId = activeCropTarget.id;
      try {
        await updateImageAltText(targetId, value.trim() || null);
        setSavedImages((prev) =>
          prev.map((i) => (i.id === targetId ? { ...i, alt_text: value.trim() || null } : i)),
        );
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      }
    },
    [activeCropTarget],
  );

  const handleRegenerate = useCallback(async () => {
    if (!activeCropTarget || activeCropTarget.kind !== "saved") return;
    const targetId = activeCropTarget.id;
    if (!tryBeginImageOp(targetId)) return;
    try {
      const raw = await regenerateImage(targetId);
      const updated = mapImageOutToProductImage(raw);
      setSavedImages((prev) => prev.map((i) => (i.id === targetId ? updated : i)));
      toast.success("Variants regenerated.");
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    } finally {
      endImageOp(targetId);
    }
  }, [activeCropTarget, tryBeginImageOp, endImageOp]);

  const addPendingImages = useCallback(
    (files: File[]) => {
      const newImgs: PendingImage[] = files.map((file) => ({
        id: uid(),
        file,
        preview: URL.createObjectURL(file),
        alt_text: "",
        crop: null,
      }));
      setPendingImages((prev) => [...prev, ...newImgs]);
      setIsDirty(true);
      // Every uploaded image immediately gets its own turn in the crop editor.
      newImgs.forEach((img) => enqueueCrop({ kind: "pending", id: img.id }));
    },
    [enqueueCrop],
  );

  const removePendingImage = useCallback((id: string) => {
    setPendingImages((prev) => {
      const img = prev.find((i) => i.id === id);
      if (img) URL.revokeObjectURL(img.preview);
      return prev.filter((i) => i.id !== id);
    });
    setCropQueue((prev) => prev.filter((t) => !(t.kind === "pending" && t.id === id)));
  }, []);

  const deleteSavedImage = useCallback(
    async (imageId: string) => {
      if (!initialProduct || !tryBeginImageOp(imageId)) return;
      try {
        await deleteMediaImage(imageId);
        setSavedImages((prev) => prev.filter((i) => i.id !== imageId));
        setCropQueue((prev) => prev.filter((t) => !(t.kind === "saved" && t.id === imageId)));
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.product(initialProduct.id) });
        queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
        toast.success("Image deleted.");
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      } finally {
        endImageOp(imageId);
      }
    },
    [initialProduct?.id, queryClient, tryBeginImageOp, endImageOp],
  );

  const setPrimarySaved = useCallback(
    async (imageId: string) => {
      if (!initialProduct || !tryBeginImageOp(imageId)) return;
      try {
        await setPrimaryImage(imageId);
        setSavedImages((prev) => prev.map((i) => ({ ...i, is_primary: i.id === imageId })));
        // Primary image drives the flat `primary_image` thumbnail every
        // products-list card renders — without this, the list keeps
        // showing the old primary until an unrelated refetch happens
        // (docs audit MP-11/LP-5).
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.product(initialProduct.id) });
        queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
        toast.success("Primary image updated.");
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      } finally {
        endImageOp(imageId);
      }
    },
    [initialProduct?.id, queryClient, tryBeginImageOp, endImageOp],
  );

  const replaceSavedImage = useCallback(
    async (imageId: string, file: File) => {
      if (!initialProduct || !tryBeginImageOp(imageId)) return;
      try {
        const raw = await replaceImage(imageId, file);
        const updated = mapImageOutToProductImage(raw);
        setSavedImages((prev) => prev.map((i) => (i.id === imageId ? updated : i)));
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.product(initialProduct.id) });
        queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
        // The new original has no crop applied yet — open the editor for it.
        enqueueCrop({ kind: "saved", id: imageId });
        toast.success("Image replaced. Crop the new image to update its display size.");
        if (raw.status !== "ready") awaitGeneration(raw.id);
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      } finally {
        endImageOp(imageId);
      }
    },
    [initialProduct?.id, queryClient, enqueueCrop, tryBeginImageOp, endImageOp, awaitGeneration],
  );

  // Swaps a saved image's gallery position with its neighbor — the API
  // (`reorderImages`) already supports arbitrary sort orders, this just
  // wasn't surfaced anywhere in the UI (docs audit MF-3).
  const moveSavedImage = useCallback(
    async (imageId: string, direction: "up" | "down") => {
      if (!initialProduct) return;
      const idx = savedImages.findIndex((i) => i.id === imageId);
      if (idx === -1) return;
      const targetIdx = direction === "up" ? idx - 1 : idx + 1;
      if (targetIdx < 0 || targetIdx >= savedImages.length) return;
      const a = savedImages[idx];
      const b = savedImages[targetIdx];
      if (busyImageIdsRef.current.has(a.id) || busyImageIdsRef.current.has(b.id)) return;
      tryBeginImageOp(a.id);
      tryBeginImageOp(b.id);
      const swap = () =>
        setSavedImages((prev) => {
          const next = [...prev];
          [next[idx], next[targetIdx]] = [next[targetIdx], next[idx]];
          return next;
        });
      swap();
      try {
        await reorderImages("product", initialProduct.id, [
          { imageId: a.id, sortOrder: targetIdx },
          { imageId: b.id, sortOrder: idx },
        ]);
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.product(initialProduct.id) });
        queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      } catch (e) {
        toast.error(toUserMessage(e as Error));
        swap();
      } finally {
        endImageOp(a.id);
        endImageOp(b.id);
      }
    },
    [savedImages, initialProduct, queryClient, tryBeginImageOp, endImageOp],
  );

  const editCropPending = useCallback(
    (id: string) => enqueueCrop({ kind: "pending", id }),
    [enqueueCrop],
  );

  const editCropSaved = useCallback(
    (id: string) => {
      // Don't queue a crop for an image that's mid delete/replace/set-primary
      // — by the time its turn comes up it may already be gone or superseded.
      if (busyImageIdsRef.current.has(id)) return;
      enqueueCrop({ kind: "saved", id });
    },
    [enqueueCrop],
  );

  const activeCropImage = useMemo(() => {
    if (!activeCropTarget) return null;
    if (activeCropTarget.kind === "pending") {
      const img = pendingImages.find((i) => i.id === activeCropTarget.id);
      if (!img) return null;
      const initialCrops = img.crop
        ? (img.crop.crops as Partial<Record<Breakpoint, BreakpointCropGeometry>>)
        : undefined;
      return { src: img.preview, initialCrops, altText: undefined as string | null | undefined };
    }
    // Saved images: wait for the fresh `getImage` fetch (savedCropFetch)
    // rather than the desktop-only fields cached on `ProductImage` — using
    // those would silently reset tablet/mobile framing to centered
    // defaults, which then overwrite the stored crops on save (docs audit
    // CB-2/HP-6). Returning null while the fetch is in flight keeps the
    // editor dialog closed; a separate loading dialog covers that gap (see
    // savedCropFetchLoading below).
    if (!savedCropFetch || savedCropFetch.id !== activeCropTarget.id) return null;
    // Always re-open the crop editor against the untouched original, never
    // a generated variant (img.url/large_url/etc) — those are already
    // cropped and resized, so their pixel coordinates don't even line up
    // with the stored crop box, let alone let the admin reposition into
    // parts of the image the previous crop discarded.
    return {
      src: savedCropFetch.originalUrl,
      initialCrops: savedCropFetch.initialCrops,
      altText: savedCropFetch.altText,
    };
  }, [activeCropTarget, pendingImages, savedCropFetch]);

  const handleCropCancel = useCallback(() => {
    dequeueCrop();
  }, [dequeueCrop]);

  const handleCropSave = useCallback(
    async ({ geometry }: UniversalImageEditorSaveResult, intent: SaveIntent) => {
      if (!activeCropTarget) return;

      if (activeCropTarget.kind === "pending") {
        // Not uploaded yet — just remember the crop, it's applied right
        // after this image's own upload call during Save.
        setPendingImages((prev) =>
          prev.map((i) => (i.id === activeCropTarget.id ? { ...i, crop: geometry } : i)),
        );
        // "Save & Continue" keeps this image's editor open (e.g. to refine
        // another breakpoint) instead of advancing the crop queue.
        if (intent === "save") dequeueCrop();
        return;
      }

      if (!initialProduct) return;
      const targetId = activeCropTarget.id;
      if (!tryBeginImageOp(targetId)) return;
      setCropSaving(true);
      try {
        const raw = await cropImage(targetId, geometry);
        const updated = mapImageOutToProductImage(raw);
        setSavedImages((prev) => prev.map((i) => (i.id === targetId ? updated : i)));
        // Keep the in-flight editor state (all breakpoints) in sync with
        // what was just persisted, so "Save & Continue" doesn't re-show
        // pre-save geometry for the next edit in this same session.
        setSavedCropFetch({
          id: targetId,
          originalUrl: raw.original_url,
          initialCrops: parseStoredCrops(raw),
          altText: raw.alt_text,
        });
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.product(initialProduct.id) });
        queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
        toast.success("Crop saved.");
        if (intent === "save") dequeueCrop();
        // Real variants aren't ready yet (raw.status === 'pending') — the
        // background worker is still generating them (docs audit CB-1
        // Phase 2). Swap in the fresh thumbnail once it finishes.
        if (raw.status !== "ready") awaitGeneration(targetId);
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      } finally {
        endImageOp(targetId);
        setCropSaving(false);
      }
    },
    [
      activeCropTarget,
      initialProduct,
      queryClient,
      dequeueCrop,
      tryBeginImageOp,
      endImageOp,
      awaitGeneration,
    ],
  );

  // ── Inline category/collection creation ──────────────────────────────────────

  const handleCategoryCreated = useCallback(
    (cat: CategoryTreeNode) => {
      setCategoryTreeLocal((prev) => {
        if (!cat.parent_id) return [...prev, cat];
        return prev.map((p) =>
          p.id === cat.parent_id ? { ...p, children: [...p.children, cat] } : p,
        );
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.categories.all });
    },
    [queryClient],
  );

  const handleCollectionCreated = useCallback(
    (col: CollectionDetail) => {
      setCollectionsLocal((prev) => [...prev, col]);
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.collections });
    },
    [queryClient],
  );

  // ── Build payload helpers ───────────────────────────────────────────────────

  function buildPayload(status: ProductStatus) {
    const f = form;
    return {
      sku: f.sku.trim(),
      name: f.name.trim(),
      slug: f.slug.trim(),
      description: f.description.trim() || undefined,
      short_description: f.short_description.trim() || undefined,
      category_id: f.category_id || undefined,
      base_price: parseFloat(f.base_price),
      compare_at_price: f.compare_at_price ? parseFloat(f.compare_at_price) : undefined,
      cost_price: f.cost_price ? parseFloat(f.cost_price) : undefined,
      tax_rate: parseFloat(f.tax_rate) || 3.0,
      hsn_code: f.hsn_code || undefined,
      track_inventory: f.track_inventory,
      stock_quantity: parseInt(f.stock_quantity) || 0,
      low_stock_threshold: parseInt(f.low_stock_threshold) || 5,
      allow_backorder: f.allow_backorder,
      metal_type: f.metal_type || undefined,
      purity: f.purity || undefined,
      hallmark_number: f.hallmark_number || undefined,
      making_charges: f.making_charges ? parseFloat(f.making_charges) : undefined,
      wastage_percent: f.wastage_percent ? parseFloat(f.wastage_percent) : undefined,
      weight_grams: f.weight_grams ? parseFloat(f.weight_grams) : undefined,
      gender: f.gender || undefined,
      is_customizable: f.is_customizable,
      requires_shipping: f.requires_shipping,
      length_cm: f.length_cm ? parseFloat(f.length_cm) : undefined,
      width_cm: f.width_cm ? parseFloat(f.width_cm) : undefined,
      height_cm: f.height_cm ? parseFloat(f.height_cm) : undefined,
      is_featured: f.is_featured,
      is_new_arrival: f.is_new_arrival,
      is_best_seller: f.is_best_seller,
      meta_title: f.meta_title || undefined,
      meta_description: f.meta_description || undefined,
      meta_keywords: f.meta_keywords || undefined,
      status,
      variants: f.enable_variants
        ? f.variants
            .filter((v) => v.id.startsWith("__"))
            .map((v, i) => ({
              sku: v.sku,
              name: v.name,
              price_adjustment: v.price_adjustment,
              stock_quantity: v.stock_quantity,
              weight_grams: v.weight_grams || undefined,
              is_active: v.is_active,
              sort_order: i,
            }))
        : [],
      attributes: f.attributes
        .filter((a) => a.name && a.value)
        .map((a, i) => ({ name: a.name, value: a.value, sort_order: i })),
    };
  }

  // ── Save handlers ───────────────────────────────────────────────────────────

  // Applies a crop chosen in the editor before this image existed on the
  // server — called right after its upload response gives us a real image id.
  // Returns the post-crop image (fresh thumbnail/medium/large) so the caller
  // can put the final, correctly-cropped row into `savedImages` directly,
  // rather than the pre-crop upload response.
  async function applyPendingCrop(
    imageId: string,
    crop: CropGeometry | null,
  ): Promise<ProductImage | null> {
    if (!crop) return null;
    const raw = await cropImage(imageId, crop);
    return mapImageOutToProductImage(raw);
  }

  async function handleCreate(publishNow: boolean) {
    const errors = validateForm(form, pendingImages, []);
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      const firstKey = Object.keys(errors)[0];
      document.getElementById(firstKey)?.scrollIntoView({ behavior: "smooth", block: "center" });
      toast.error("Please fix validation errors.");
      return;
    }
    setFormErrors({});
    setSaving(true);
    try {
      const status: ProductStatus = publishNow ? "active" : "draft";
      const product = await api.post<ProductDetail>("/admin/products", {
        body: buildPayload(status),
      });

      for (let i = 0; i < pendingImages.length; i++) {
        const img = pendingImages[i];
        const raw = await uploadImage({
          presetId: "product",
          file: img.file,
          ownerType: "product",
          ownerId: product.id,
        });
        if (i === 0) await setPrimaryImage(raw.id);
        const cropped = await applyPendingCrop(raw.id, img.crop);
        const final = cropped ?? mapImageOutToProductImage(raw);
        setSavedImages((prev) => [...prev, i === 0 ? { ...final, is_primary: true } : final]);
        if (raw.status !== "ready") awaitGeneration(raw.id);
      }
      setPendingImages([]);

      for (const colId of form.collection_ids) {
        await api.post(`/admin/collections/${colId}/products`, {
          body: { product_ids: [product.id] },
        });
      }

      queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      toast.success(publishNow ? "Product published!" : "Draft saved.");
      navigate({ to: "/admin/products" });
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdate(publishNow: boolean) {
    if (!initialProduct) return;
    const errors = validateForm(form, pendingImages, savedImages);
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      const firstKey = Object.keys(errors)[0];
      document.getElementById(firstKey)?.scrollIntoView({ behavior: "smooth", block: "center" });
      toast.error("Please fix validation errors.");
      return;
    }
    setFormErrors({});
    setSaving(true);
    const pid = initialProduct.id;
    try {
      const status: ProductStatus = publishNow ? "active" : form.status;
      await api.patch(`/admin/products/${pid}`, { body: buildPayload(status) });

      // Upload new images
      for (let i = 0; i < pendingImages.length; i++) {
        const img = pendingImages[i];
        const isPrimary = savedImages.length === 0 && i === 0;
        const raw = await uploadImage({
          presetId: "product",
          file: img.file,
          ownerType: "product",
          ownerId: pid,
        });
        if (isPrimary) await setPrimaryImage(raw.id);
        const cropped = await applyPendingCrop(raw.id, img.crop);
        const final = cropped ?? mapImageOutToProductImage(raw);
        // Put the final (post-crop, if any) row straight into local state —
        // don't wait on the query invalidation below to repopulate it, since
        // that only refetches in the background and won't re-sync this
        // form's local `savedImages` (see the initialProduct?.id-keyed sync
        // effect above, which intentionally doesn't re-run on every refetch).
        setSavedImages((prev) => [...prev, isPrimary ? { ...final, is_primary: true } : final]);
        if (raw.status !== "ready") awaitGeneration(raw.id);
      }
      setPendingImages([]);

      // Variant deletes
      for (const vid of deletedVariantIds) {
        await api.delete(`/admin/products/variants/${vid}`);
      }
      setDeletedVariantIds([]);

      // Variant creates/updates
      for (const [i, v] of form.variants.entries()) {
        const vPayload = {
          sku: v.sku,
          name: v.name,
          price_adjustment: v.price_adjustment,
          stock_quantity: v.stock_quantity,
          weight_grams: v.weight_grams || undefined,
          is_active: v.is_active,
          sort_order: i,
        };
        if (v.id.startsWith("__")) {
          await api.post(`/admin/products/${pid}/variants`, { body: vPayload });
        } else {
          await api.patch(`/admin/products/variants/${v.id}`, { body: vPayload });
        }
      }

      // Attribute deletes
      for (const name of deletedAttributeNames) {
        await api.delete(`/admin/products/${pid}/attributes/${encodeURIComponent(name)}`);
      }
      setDeletedAttributeNames([]);

      // Attribute upserts
      for (const [i, attr] of form.attributes.filter((a) => a.name && a.value).entries()) {
        await api.put(`/admin/products/${pid}/attributes`, {
          body: { name: attr.name, value: attr.value, sort_order: i },
        });
      }

      // Collection changes
      const prevIds = initialCollectionIdsRef.current;
      const added = form.collection_ids.filter((id) => !prevIds.includes(id));
      const removed = prevIds.filter((id) => !form.collection_ids.includes(id));
      for (const colId of added) {
        await api.post(`/admin/collections/${colId}/products`, { body: { product_ids: [pid] } });
      }
      for (const colId of removed) {
        await api.delete(`/admin/collections/${colId}/products/${pid}`);
      }
      initialCollectionIdsRef.current = form.collection_ids;

      queryClient.invalidateQueries({ queryKey: queryKeys.admin.product(pid) });
      queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      setIsDirty(false);
      toast.success(publishNow ? "Product published!" : "Product updated.");
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    } finally {
      setSaving(false);
    }
  }

  const handleSaveDraft = () => (mode === "new" ? handleCreate(false) : handleUpdate(false));
  const handlePublish = () => (mode === "new" ? handleCreate(true) : handleUpdate(true));

  // ── Derived state ───────────────────────────────────────────────────────────

  const selectedCategoryName =
    categoryTreeLocal.flatMap((p) => p.children).find((c) => c.id === form.category_id)?.name ?? "";

  const selectedCollectionNames = (collectionsLocal.length ? collectionsLocal : collections)
    .filter((c) => form.collection_ids.includes(c.id))
    .map((c) => c.name);

  // Track variant deletions in edit mode
  const handleSetForm = useCallback(
    (patch: Partial<FormState>) => {
      if (patch.variants && initialProduct) {
        const currentIds = form.variants.map((v) => v.id).filter((id) => !id.startsWith("__"));
        const nextIds = (patch.variants as LocalVariant[])
          .map((v) => v.id)
          .filter((id) => !id.startsWith("__"));
        const newlyDeleted = currentIds.filter((id) => !nextIds.includes(id));
        if (newlyDeleted.length) {
          setDeletedVariantIds((prev) => [...new Set([...prev, ...newlyDeleted])]);
        }
      }
      if (patch.attributes && initialProduct) {
        const currentNames = form.attributes.map((a) => a.name);
        const nextNames = (patch.attributes as LocalAttribute[]).map((a) => a.name);
        const newlyDeleted = currentNames.filter((n) => n && !nextNames.includes(n));
        if (newlyDeleted.length) {
          setDeletedAttributeNames((prev) => [...new Set([...prev, ...newlyDeleted])]);
        }
      }
      set(patch);
    },
    [form.variants, form.attributes, initialProduct, set],
  );

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-secondary/20">
      {/* Sticky header */}
      <div className="sticky top-0 z-30 bg-background border-b border-border px-6 py-4 flex items-center gap-4">
        <button
          type="button"
          onClick={() => navigate({ to: "/admin/products" })}
          className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground"
        >
          ← Products
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
            {mode === "new" ? "New Product" : "Edit Product"}
          </p>
          <h1 className="font-display text-xl truncate mt-0.5">
            {form.name || (mode === "new" ? "Untitled Product" : "—")}
          </h1>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {isDirty && (
            <span className="text-[11px] text-amber-600 hidden sm:block">Unsaved changes</span>
          )}
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={saving}
            className="flex items-center justify-center gap-2 border border-border text-[11px] uppercase tracking-[0.22em] px-4 py-2.5 hover:bg-secondary disabled:opacity-50"
          >
            {saving && <Loader2 className="size-3.5 animate-spin" />}
            {saving ? "Saving…" : "Save Draft"}
          </button>
          <button
            type="button"
            onClick={handlePublish}
            disabled={saving}
            className="flex items-center justify-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-4 py-2.5 hover:opacity-90 disabled:opacity-50"
          >
            {saving && <Loader2 className="size-3.5 animate-spin" />}
            {saving ? "Saving…" : "Publish"}
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="max-w-[1280px] mx-auto px-6 py-8 flex gap-6 items-start">
        {/* Left: sections */}
        <div className="flex-1 min-w-0 flex flex-col gap-4">
          <Section
            title="Product Information"
            error={
              !!(
                formErrors.name ||
                formErrors.sku ||
                formErrors.slug ||
                formErrors.short_description ||
                formErrors.description
              )
            }
          >
            <ProductInfoSection
              form={form}
              set={handleSetForm}
              errors={formErrors}
              onGenerateSku={generateSku}
              skuLoading={skuLoading}
            />
          </Section>

          <Section title="Organization" error={!!formErrors.category_id}>
            <OrganizationSection
              form={form}
              set={handleSetForm}
              errors={formErrors}
              categoryTree={categoryTreeLocal.length ? categoryTreeLocal : categoryTree}
              collections={collectionsLocal.length ? collectionsLocal : collections}
              onCategoryCreated={handleCategoryCreated}
              onCollectionCreated={handleCollectionCreated}
            />
          </Section>

          <Section title="Pricing" error={!!formErrors.base_price}>
            <PricingSection form={form} set={handleSetForm} errors={formErrors} />
          </Section>

          <Section title="Inventory" defaultOpen={false}>
            <InventorySection form={form} set={handleSetForm} />
          </Section>

          <Section title="Jewellery Details" defaultOpen={false}>
            <JewellerySection form={form} set={handleSetForm} />
          </Section>

          <Section title="Media" error={!!formErrors.images}>
            <MediaSection
              productId={initialProduct?.id}
              pendingImages={pendingImages}
              savedImages={savedImages}
              onAddPending={addPendingImages}
              onRemovePending={removePendingImage}
              onSetPrimaryPending={(id) =>
                setPendingImages((prev) => prev.map((i, idx) => ({ ...i })))
              }
              onDeleteSaved={deleteSavedImage}
              onSetPrimarySaved={setPrimarySaved}
              onEditCropPending={editCropPending}
              onEditCropSaved={editCropSaved}
              onReplaceSaved={replaceSavedImage}
              onMoveSaved={moveSavedImage}
              busyImageIds={busyImageIds}
              generatingImageIds={generatingImageIds}
              error={formErrors.images}
            />
          </Section>

          {activeCropTarget?.kind === "saved" && savedCropFetchLoading && (
            <Dialog open onOpenChange={(open) => !open && handleCropCancel()}>
              <DialogContent>
                <DialogTitle className="sr-only">Loading image</DialogTitle>
                <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Loading original image…
                </div>
              </DialogContent>
            </Dialog>
          )}

          {activeCropImage && (
            <UniversalImageEditor
              open
              onOpenChange={(open) => !open && handleCropCancel()}
              preset={PRODUCT_PRESET}
              existingImageSrc={activeCropImage.src}
              initialCrops={activeCropImage.initialCrops}
              saving={cropSaving}
              onCancel={handleCropCancel}
              onSave={handleCropSave}
              initialAltText={
                activeCropTarget?.kind === "saved" ? activeCropImage.altText : undefined
              }
              onAltTextCommit={activeCropTarget?.kind === "saved" ? handleAltTextCommit : undefined}
              onRegenerate={activeCropTarget?.kind === "saved" ? handleRegenerate : undefined}
              regenerating={
                activeCropTarget?.kind === "saved" && busyImageIds.has(activeCropTarget.id)
              }
            />
          )}

          <Section title="Variants" defaultOpen={false}>
            <VariantsSection form={form} set={handleSetForm} baseSku={form.sku} />
          </Section>

          <Section title="Attributes" defaultOpen={false}>
            <AttributesSection form={form} set={handleSetForm} />
          </Section>

          <Section title="SEO" defaultOpen={false}>
            <SeoSection
              form={form}
              set={handleSetForm}
              mode={mode}
              categoryName={selectedCategoryName}
              collectionNames={selectedCollectionNames}
              seoEdited={seoEdited}
              onSetSeoEdited={updateSeoEdited}
            />
          </Section>
        </div>

        {/* Right: sidebar */}
        <div className="w-72 shrink-0 sticky top-[73px]">
          <PublishSidebar
            form={form}
            set={handleSetForm}
            mode={mode}
            saving={saving}
            onSaveDraft={handleSaveDraft}
            onPublish={handlePublish}
            onCancel={() => navigate({ to: "/admin/products" })}
            isDirty={isDirty}
            pendingImagesCount={pendingImages.length}
            savedImagesCount={savedImages.length}
            collectionsCount={form.collection_ids.length}
            variantsCount={form.variants.length}
            selectedCategory={selectedCategoryName}
          />
        </div>
      </div>
    </div>
  );
}
