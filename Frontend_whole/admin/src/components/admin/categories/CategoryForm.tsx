import { useCallback, useRef, useState, useEffect } from "react";
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
  getImage,
  pollImageUntilReady,
  bustCacheUrl,
  regenerateImage,
  updateImageAltText,
  type SaveIntent,
  type UniversalImageEditorSaveResult,
  type ImageOutRaw,
} from "@hadha/shared-media";
import { PRESET_REGISTRY, type Breakpoint, type BreakpointCropGeometry } from "@hadha/shared-types";
import { Dialog, DialogContent, DialogTitle } from "@hadha/shared-ui/ui/dialog";
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

/** Parses ImageOutRaw's metadata.crops back into the shape UniversalImageEditor
 * seeds itself from — mirrors CollectionForm's equivalent parse. */
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
  for (const bp of CATEGORY_PRESET.breakpoints) {
    const c = crops[bp];
    if (!c) continue;
    result[bp] = {
      aspectRatio: CATEGORY_PRESET.aspectRatio[bp] ?? null,
      box: c.box,
      zoom: c.zoom,
      pan: { x: 0, y: 0 },
      rotation: c.rotation,
    };
  }
  return Object.keys(result).length > 0 ? result : undefined;
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
  // Lets awaitGeneration's async poll check, once it resolves, whether the
  // image it was waiting on is still the one in play — the admin could have
  // removed/replaced it while generation was still running in the background.
  const imageIdRef = useRef(imageId);
  useEffect(() => {
    imageIdRef.current = imageId;
  }, [imageId]);
  // The untouched original + its previously-saved crop geometry — fetched
  // fresh each time the editor opens on an existing image (see the effect
  // below) rather than trusting `imageUrl`, which is a generated variant
  // and must never be handed to the crop editor.
  const [editorOriginalUrl, setEditorOriginalUrl] = useState<string | null>(null);
  const [editorInitialCrops, setEditorInitialCrops] = useState<
    Partial<Record<Breakpoint, BreakpointCropGeometry>> | undefined
  >(undefined);
  const [editorAltText, setEditorAltText] = useState<string | null>(null);
  const [editorLoading, setEditorLoading] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  // Covers both save (upload/crop) and remove — the two are mutually exclusive
  // on this single-cover image slot, so one flag can gate both UI affordances.
  const [imageBusy, setImageBusy] = useState(false);
  // True while the background worker is still generating this image's
  // variants (docs audit CB-1 Phase 2 — crop/upload now return with
  // status='pending' almost immediately, well before real variants exist).
  const [imageGenerating, setImageGenerating] = useState(false);
  // React state updates are async, so a `useState` check alone can't stop a
  // second click fired in the same tick (before the disabled re-render lands)
  // from re-entering these handlers and racing crop/remove against each
  // other on the same image id. A ref is set synchronously, closing that gap.
  const imageOpInFlight = useRef(false);

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

  // Re-fetch the image's true original + saved crop geometry every time the
  // editor opens on an existing image, rather than trusting local state —
  // guarantees "Edit Crop" always operates on the untouched original.
  useEffect(() => {
    if (!editorOpen || !imageId) return;
    let cancelled = false;
    setEditorLoading(true);
    getImage(imageId)
      .then((raw) => {
        if (cancelled) return;
        setEditorOriginalUrl(raw.original_url);
        setEditorInitialCrops(parseStoredCrops(raw));
        setEditorAltText(raw.alt_text);
      })
      .catch((e) => {
        if (cancelled) return;
        toast.error(toUserMessage(e as Error));
        setEditorOpen(false);
      })
      .finally(() => {
        if (!cancelled) setEditorLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [editorOpen, imageId]);

  const handleAltTextCommit = useCallback(
    async (value: string) => {
      if (!imageId) return;
      try {
        await updateImageAltText(imageId, value.trim() || null);
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      }
    },
    [imageId],
  );

  const handleRegenerate = useCallback(async () => {
    if (!imageId) return;
    setImageBusy(true);
    try {
      const raw = await regenerateImage(imageId);
      setImageUrl(pickPreviewUrl(raw));
      toast.success("Variants regenerated.");
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    } finally {
      setImageBusy(false);
    }
  }, [imageId]);

  // Fire-and-forget: waits for the background worker to actually finish
  // generating variants, then swaps in the real thumbnail. Never blocks the
  // save flow — crop/upload already returned and the dialog/toast have
  // moved on by the time this resolves (docs audit CB-1 Phase 2).
  const awaitGeneration = useCallback(
    async (targetImageId: string) => {
      setImageGenerating(true);
      try {
        const fresh = await pollImageUntilReady(targetImageId);
        if (targetImageId !== imageIdRef.current) return; // superseded meanwhile
        const url = pickPreviewUrl(fresh);
        setImageUrl(url ? bustCacheUrl(url) : url);
        if (category?.id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.admin.categories });
          queryClient.invalidateQueries({ queryKey: queryKeys.admin.category(category.id) });
        }
      } catch (e) {
        toast.error(toUserMessage(e as Error) || "Image processing failed — try again.");
      } finally {
        setImageGenerating(false);
      }
    },
    [category?.id, queryClient],
  );

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
    async ({ file, geometry }: UniversalImageEditorSaveResult, intent: SaveIntent) => {
      if (imageOpInFlight.current) return;
      imageOpInFlight.current = true;
      setImageBusy(true);
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
        setEditorOriginalUrl(raw.original_url);
        setEditorInitialCrops(parseStoredCrops(raw));
        setEditorAltText(raw.alt_text);
        // Crop/upload here persists to the media API immediately, independent
        // of the form's own submit — without this, the categories list and
        // this category's detail query keep serving the pre-edit thumbnail
        // until an unrelated form submit happens to refetch them (docs audit
        // MP-11/LP-5). A brand-new category has no id yet, so there's
        // nothing cached to invalidate.
        if (category?.id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.admin.categories });
          queryClient.invalidateQueries({ queryKey: queryKeys.admin.category(category.id) });
        }
        if (intent === "save") {
          setEditorOpen(false);
          toast.success("Image saved.");
        } else {
          toast.success("Crop saved.");
        }
        // Real variants aren't ready yet (raw.status === 'pending') — the
        // background worker is still generating them (docs audit CB-1
        // Phase 2). Swap in the fresh thumbnail once it finishes, without
        // blocking the save flow above.
        if (raw.status !== "ready") void awaitGeneration(raw.id);
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      } finally {
        imageOpInFlight.current = false;
        setImageBusy(false);
      }
    },
    [category?.id, imageId, queryClient, awaitGeneration],
  );

  const handleRemoveImage = useCallback(async () => {
    if (!imageId || imageOpInFlight.current) return;
    imageOpInFlight.current = true;
    setImageBusy(true);
    try {
      await deleteMediaImage(imageId);
      setImageId(null);
      setImageUrl(null);
      setEditorOriginalUrl(null);
      setEditorInitialCrops(undefined);
      setEditorAltText(null);
      if (category?.id) {
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.categories });
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.category(category.id) });
      }
      toast.success("Image removed.");
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    } finally {
      imageOpInFlight.current = false;
      setImageBusy(false);
    }
  }, [imageId, category?.id, queryClient]);

  const handleDeleteFromEditor = useCallback(() => {
    if (!imageId) return;
    if (!confirm("Remove this image?")) return;
    setEditorOpen(false);
    void handleRemoveImage();
  }, [imageId, handleRemoveImage]);

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
                  {imageGenerating && (
                    <div className="absolute bottom-2 right-2 flex items-center gap-1.5 bg-background/90 text-foreground text-[11px] px-2 py-1 rounded-sm shadow-sm">
                      <Loader2 className="size-3 animate-spin" />
                      Generating variants…
                    </div>
                  )}
                  <div className="absolute inset-0 bg-foreground/0 group-hover:bg-foreground/40 transition-all flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => setEditorOpen(true)}
                      disabled={imageBusy}
                      className="bg-background text-foreground text-xs px-3 py-1.5 hover:bg-secondary transition flex items-center gap-1.5 disabled:opacity-60"
                    >
                      {imageBusy ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <CropIcon className="size-3.5" />
                      )}
                      Edit crop
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (confirm("Remove this image?")) handleRemoveImage();
                      }}
                      disabled={imageBusy}
                      className="bg-destructive text-destructive-foreground text-xs px-3 py-1.5 hover:opacity-90 transition flex items-center gap-1.5 disabled:opacity-60"
                    >
                      {imageBusy ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="size-3.5" />
                      )}
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

            {editorOpen && editorLoading && (
              <Dialog open onOpenChange={(open) => !open && setEditorOpen(false)}>
                <DialogContent>
                  <DialogTitle className="sr-only">Loading image</DialogTitle>
                  <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Loading original image…
                  </div>
                </DialogContent>
              </Dialog>
            )}
            <UniversalImageEditor
              open={editorOpen && !editorLoading}
              onOpenChange={(open) => !open && setEditorOpen(false)}
              preset={CATEGORY_PRESET}
              // Re-editing an existing image must always operate on the
              // untouched original (editorOriginalUrl, fetched fresh above)
              // — never `imageUrl`, which is a generated variant. A
              // brand-new image (no imageId yet) has no original to fetch,
              // so it's undefined.
              existingImageSrc={imageId ? (editorOriginalUrl ?? undefined) : undefined}
              initialCrops={imageId ? editorInitialCrops : undefined}
              saving={imageBusy}
              onCancel={() => setEditorOpen(false)}
              onSave={handleImageSave}
              onDelete={imageId ? handleDeleteFromEditor : undefined}
              initialAltText={editorAltText}
              onAltTextCommit={imageId ? handleAltTextCommit : undefined}
              onRegenerate={imageId ? handleRegenerate : undefined}
              regenerating={imageBusy}
            />

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
                {mutation.isPending
                  ? mode === "new"
                    ? "Creating…"
                    : "Saving…"
                  : mode === "new"
                    ? "Create Category"
                    : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
