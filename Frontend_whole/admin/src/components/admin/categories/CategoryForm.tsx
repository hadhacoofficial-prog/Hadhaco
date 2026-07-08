import { useCallback, useState, useEffect } from "react";
import { useNavigate, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Crop as CropIcon, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import {
  UniversalImageEditor,
  uploadImage,
  cropImage,
  attachImage,
  setPrimaryImage,
  deleteImage as deleteMediaImage,
  type UniversalImageEditorSaveResult,
  type ImageOutRaw,
} from "@hadha/shared-media";
import { PRESET_REGISTRY } from "@hadha/shared-types";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@hadha/shared-ui/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import type { CategoryDetail, CategoryAdminListResponse } from "@/types/admin";

const CATEGORY_PRESET = PRESET_REGISTRY.category;

function pickPreviewUrl(raw: ImageOutRaw): string | null {
  const ready = raw.variants.filter(
    (v) => v.breakpoint === "desktop" && v.dpr === 1 && v.status === "ready",
  );
  return (
    ready.find((v) => v.variant_name === "medium")?.url ??
    ready.find((v) => v.variant_name === "large")?.url ??
    ready[0]?.url ??
    null
  );
}

function toSlug(name: string) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

interface CategoryFormProps {
  mode: "new" | "edit";
  category?: CategoryDetail;
}

interface FormState {
  name: string;
  slug: string;
  description: string;
  parent_id: string;
  sort_order: string;
  is_active: boolean;
  seo_title: string;
  seo_description: string;
}

function emptyForm(): FormState {
  return {
    name: "",
    slug: "",
    description: "",
    parent_id: "",
    sort_order: "0",
    is_active: true,
    seo_title: "",
    seo_description: "",
  };
}

function fromCategory(c: CategoryDetail): FormState {
  return {
    name: c.name,
    slug: c.slug,
    description: c.description ?? "",
    parent_id: c.parent_id ?? "",
    sort_order: String(c.sort_order),
    is_active: c.is_active,
    seo_title: c.seo_title ?? "",
    seo_description: c.seo_description ?? "",
  };
}

export function CategoryForm({ mode, category }: CategoryFormProps) {
  const [form, setForm] = useState<FormState>(
    mode === "edit" && category ? fromCategory(category) : emptyForm(),
  );
  const [slugManual, setSlugManual] = useState(mode === "edit");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const [imageId, setImageId] = useState<string | null>(category?.primary_image_id ?? null);
  const [imageUrl, setImageUrl] = useState<string | null>(category?.image_url ?? null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [imageSaving, setImageSaving] = useState(false);

  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: categoriesData } = useQuery({
    queryKey: queryKeys.admin.categoriesList({}),
    queryFn: () =>
      api.get<CategoryAdminListResponse>("/admin/categories", {
        params: { page_size: 200 },
      }),
    staleTime: 60_000,
  });

  const parentOptions = (categoriesData?.items ?? []).filter(
    (c) => !category || c.id !== category.id,
  );

  useEffect(() => {
    if (!slugManual && mode === "new") {
      setForm((f) => ({ ...f, slug: toSlug(f.name) }));
    }
  }, [form.name, slugManual, mode]);

  const mutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      const result =
        mode === "new"
          ? await api.post<CategoryDetail>("/admin/categories", { body: data })
          : await api.patch<CategoryDetail>(`/admin/categories/${category!.id}`, { body: data });
      // New categories don't have an id yet when the image is uploaded, so
      // it's uploaded unattached — attach it now that the owner id exists.
      if (mode === "new" && imageId) {
        await attachImage(imageId, "category", result.id);
        await setPrimaryImage(imageId);
      }
      return result;
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.categories });
      if (mode === "edit") {
        queryClient.invalidateQueries({
          queryKey: queryKeys.admin.category(category!.id),
        });
      }
      toast.success(mode === "new" ? "Category created!" : "Category updated!");
      navigate({ to: "/admin/categories/$categoryId", params: { categoryId: result.id } });
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const handleImageSave = useCallback(
    async ({ file, geometry }: UniversalImageEditorSaveResult) => {
      setImageSaving(true);
      try {
        let raw: ImageOutRaw;
        if (file) {
          raw = await uploadImage({
            presetId: "category",
            file,
            ownerType: "category",
            ownerId: category?.id,
          });
          raw = await cropImage(raw.id, geometry);
          if (category?.id) await setPrimaryImage(raw.id);
        } else if (imageId) {
          raw = await cropImage(imageId, geometry);
        } else {
          return;
        }
        setImageId(raw.id);
        setImageUrl(pickPreviewUrl(raw));
        setEditorOpen(false);
        toast.success("Image saved.");
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      } finally {
        setImageSaving(false);
      }
    },
    [category?.id, imageId],
  );

  const handleRemoveImage = useCallback(async () => {
    if (!imageId) return;
    try {
      await deleteMediaImage(imageId);
      setImageId(null);
      setImageUrl(null);
      toast.success("Image removed.");
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    }
  }, [imageId]);

  function set(field: keyof FormState, value: unknown) {
    setForm((f) => ({ ...f, [field]: value }));
    if (errors[field]) setErrors((e) => ({ ...e, [field]: "" }));
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!form.name.trim()) errs.name = "Name is required";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      slug: form.slug.trim() || toSlug(form.name.trim()),
      description: form.description.trim() || null,
      parent_id: form.parent_id || null,
      sort_order: parseInt(form.sort_order) || 0,
      is_active: form.is_active,
      seo_title: form.seo_title.trim() || null,
      seo_description: form.seo_description.trim() || null,
    };
    mutation.mutate(payload);
  }

  return (
    <div>
      <header className="flex items-center gap-4 mb-8">
        <button
          onClick={() => navigate({ to: "/admin/categories" })}
          className="text-muted-foreground hover:text-foreground transition"
        >
          <ArrowLeft className="size-5" />
        </button>
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Categories</p>
          <h1 className="font-display text-3xl mt-0.5">
            {mode === "new" ? "New Category" : "Edit Category"}
          </h1>
        </div>
      </header>

      <form onSubmit={handleSubmit}>
        <div className="grid lg:grid-cols-[1fr_320px] gap-6">
          {/* Left column */}
          <div className="space-y-6">
            <section className="bg-background border border-border p-6 space-y-4">
              <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
                Basic Info
              </h2>

              <div>
                <label className="block text-xs mb-1.5">Name *</label>
                <input
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition"
                  placeholder="e.g. Rings"
                />
                {errors.name && <p className="text-xs text-destructive mt-1">{errors.name}</p>}
              </div>

              <div>
                <label className="block text-xs mb-1.5">Slug</label>
                <div className="flex gap-2 items-center">
                  <input
                    value={form.slug}
                    onChange={(e) => {
                      setSlugManual(true);
                      set("slug", e.target.value);
                    }}
                    className="flex-1 border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition font-mono"
                    placeholder="rings"
                  />
                  {mode === "new" && (
                    <button
                      type="button"
                      onClick={() => {
                        setSlugManual(false);
                        set("slug", toSlug(form.name));
                      }}
                      className="text-[10px] text-muted-foreground hover:text-foreground transition px-2 py-1 border border-border"
                    >
                      Auto
                    </button>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-xs mb-1.5">Parent Category</label>
                <select
                  value={form.parent_id}
                  onChange={(e) => set("parent_id", e.target.value)}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition"
                >
                  <option value="">— Top level —</option>
                  {parentOptions.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.parent_id ? `  ↳ ` : ""}
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs mb-1.5">Description</label>
                <textarea
                  value={form.description}
                  onChange={(e) => set("description", e.target.value)}
                  rows={3}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition resize-none"
                  placeholder="Optional description…"
                />
              </div>
            </section>

            <section className="bg-background border border-border p-6 space-y-4">
              <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">SEO</h2>
              <div>
                <label className="block text-xs mb-1.5">SEO Title</label>
                <input
                  value={form.seo_title}
                  onChange={(e) => set("seo_title", e.target.value)}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition"
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5">SEO Description</label>
                <textarea
                  value={form.seo_description}
                  onChange={(e) => set("seo_description", e.target.value)}
                  rows={3}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition resize-none"
                />
              </div>
            </section>
          </div>

          {/* Right column */}
          <div className="space-y-6">
            <section className="bg-background border border-border p-6 space-y-4">
              <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
                Settings
              </h2>
              <div className="flex items-center justify-between">
                <Label htmlFor="is_active" className="text-sm cursor-pointer">
                  Active
                </Label>
                <Switch
                  id="is_active"
                  checked={form.is_active}
                  onCheckedChange={(v) => set("is_active", v)}
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5">Sort Order</label>
                <input
                  type="number"
                  value={form.sort_order}
                  onChange={(e) => set("sort_order", e.target.value)}
                  min={0}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition"
                />
              </div>
            </section>

            <section className="bg-background border border-border p-6 space-y-3">
              <p className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground">
                Category Image
              </p>
              {imageUrl ? (
                <div className="relative group w-full aspect-video bg-secondary overflow-hidden border border-border">
                  <img src={imageUrl} alt="" className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-foreground/0 group-hover:bg-foreground/40 transition-all flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => setEditorOpen(true)}
                      className="bg-background text-foreground text-xs px-3 py-1.5 hover:bg-secondary transition flex items-center gap-1.5"
                    >
                      <CropIcon className="size-3.5" />
                      Edit crop
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (confirm("Remove this image?")) handleRemoveImage();
                      }}
                      className="bg-destructive text-destructive-foreground text-xs px-3 py-1.5 hover:opacity-90 transition flex items-center gap-1.5"
                    >
                      <Trash2 className="size-3.5" />
                      Remove
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setEditorOpen(true)}
                  className="w-full aspect-video border-2 border-dashed border-border bg-secondary/40 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-foreground/40 transition-colors"
                >
                  <p className="text-xs text-muted-foreground">Click to add an image</p>
                </button>
              )}
            </section>

            {editorOpen && (
              <Dialog open onOpenChange={(open) => !open && setEditorOpen(false)}>
                <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>Category image</DialogTitle>
                  </DialogHeader>
                  <UniversalImageEditor
                    preset={CATEGORY_PRESET}
                    existingImageSrc={imageUrl ?? undefined}
                    saving={imageSaving}
                    onCancel={() => setEditorOpen(false)}
                    onSave={handleImageSave}
                  />
                </DialogContent>
              </Dialog>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => navigate({ to: "/admin/categories" })}
                className="flex-1 border border-border py-2.5 text-sm hover:bg-secondary transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={mutation.isPending}
                className="flex-1 bg-foreground text-background py-2.5 text-sm hover:opacity-90 transition disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {mutation.isPending && <Loader2 className="size-3.5 animate-spin" />}
                {mode === "new" ? "Create Category" : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
