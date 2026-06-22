import { useState, useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { ImageUpload } from "@/components/admin/ImageUpload";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import type { CollectionDetail } from "@/types/admin";

function toSlug(name: string) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

interface CollectionFormProps {
  mode: "new" | "edit";
  collection?: CollectionDetail;
}

interface FormState {
  name: string;
  slug: string;
  description: string;
  image_url: string;
  is_active: boolean;
  is_featured: boolean;
  sort_order: string;
  seo_title: string;
  seo_description: string;
  starts_at: string;
  ends_at: string;
}

function emptyForm(): FormState {
  return {
    name: "",
    slug: "",
    description: "",
    image_url: "",
    is_active: true,
    is_featured: false,
    sort_order: "0",
    seo_title: "",
    seo_description: "",
    starts_at: "",
    ends_at: "",
  };
}

function fromCollection(c: CollectionDetail): FormState {
  return {
    name: c.name,
    slug: c.slug,
    description: c.description ?? "",
    image_url: c.image_url ?? "",
    is_active: c.is_active,
    is_featured: c.is_featured,
    sort_order: String(c.sort_order),
    seo_title: c.seo_title ?? "",
    seo_description: c.seo_description ?? "",
    starts_at: c.starts_at ? c.starts_at.slice(0, 16) : "",
    ends_at: c.ends_at ? c.ends_at.slice(0, 16) : "",
  };
}

export function CollectionForm({ mode, collection }: CollectionFormProps) {
  const [form, setForm] = useState<FormState>(
    mode === "edit" && collection ? fromCollection(collection) : emptyForm()
  );
  const [slugManual, setSlugManual] = useState(mode === "edit");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!slugManual && mode === "new") {
      setForm((f) => ({ ...f, slug: toSlug(f.name) }));
    }
  }, [form.name, slugManual, mode]);

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      mode === "new"
        ? api.post<CollectionDetail>("/admin/collections", { body: data })
        : api.patch<CollectionDetail>(`/admin/collections/${collection!.id}`, { body: data }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.collections });
      if (mode === "edit") {
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.collection(collection!.id) });
      }
      toast.success(mode === "new" ? "Collection created!" : "Collection updated!");
      navigate({ to: "/admin/collections/$collectionId", params: { collectionId: result.id } });
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  function set(field: keyof FormState, value: unknown) {
    setForm((f) => ({ ...f, [field]: value }));
    if (errors[field]) setErrors((e) => ({ ...e, [field]: "" }));
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!form.name.trim()) errs.name = "Name is required";
    if (!form.slug.trim()) errs.slug = "Slug is required";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      slug: form.slug.trim(),
      description: form.description.trim() || null,
      image_url: form.image_url.trim() || null,
      is_active: form.is_active,
      is_featured: form.is_featured,
      sort_order: parseInt(form.sort_order) || 0,
      seo_title: form.seo_title.trim() || null,
      seo_description: form.seo_description.trim() || null,
      starts_at: form.starts_at || null,
      ends_at: form.ends_at || null,
    };
    mutation.mutate(payload);
  }

  const uploadUrl = collection ? `/admin/collections/${collection.id}/image` : "";

  return (
    <div>
      <header className="flex items-center gap-4 mb-8">
        <button
          onClick={() => navigate({ to: "/admin/collections" })}
          className="text-muted-foreground hover:text-foreground transition"
        >
          <ArrowLeft className="size-5" />
        </button>
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
            Collections
          </p>
          <h1 className="font-display text-3xl mt-0.5">
            {mode === "new" ? "New Collection" : "Edit Collection"}
          </h1>
        </div>
      </header>

      <form onSubmit={handleSubmit}>
        <div className="grid lg:grid-cols-[1fr_320px] gap-6">
          {/* Left column */}
          <div className="space-y-6">
            {/* Basic info */}
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
                  placeholder="e.g. Wedding Collection"
                />
                {errors.name && (
                  <p className="text-xs text-destructive mt-1">{errors.name}</p>
                )}
              </div>

              <div>
                <label className="block text-xs mb-1.5">Slug *</label>
                <div className="flex gap-2 items-center">
                  <input
                    value={form.slug}
                    onChange={(e) => {
                      setSlugManual(true);
                      set("slug", e.target.value);
                    }}
                    className="flex-1 border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition font-mono"
                    placeholder="wedding-collection"
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
                {errors.slug && (
                  <p className="text-xs text-destructive mt-1">{errors.slug}</p>
                )}
              </div>

              <div>
                <label className="block text-xs mb-1.5">Description</label>
                <textarea
                  value={form.description}
                  onChange={(e) => set("description", e.target.value)}
                  rows={4}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition resize-none"
                  placeholder="Optional description…"
                />
              </div>
            </section>

            {/* SEO */}
            <section className="bg-background border border-border p-6 space-y-4">
              <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
                SEO
              </h2>
              <div>
                <label className="block text-xs mb-1.5">SEO Title</label>
                <input
                  value={form.seo_title}
                  onChange={(e) => set("seo_title", e.target.value)}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition"
                  placeholder="Override the page title for search engines"
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5">SEO Description</label>
                <textarea
                  value={form.seo_description}
                  onChange={(e) => set("seo_description", e.target.value)}
                  rows={3}
                  className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition resize-none"
                  placeholder="Override the meta description"
                />
              </div>
            </section>

            {/* Date range */}
            <section className="bg-background border border-border p-6 space-y-4">
              <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
                Date Range
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs mb-1.5">Start Date</label>
                  <input
                    type="datetime-local"
                    value={form.starts_at}
                    onChange={(e) => set("starts_at", e.target.value)}
                    className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition"
                  />
                </div>
                <div>
                  <label className="block text-xs mb-1.5">End Date</label>
                  <input
                    type="datetime-local"
                    value={form.ends_at}
                    onChange={(e) => set("ends_at", e.target.value)}
                    className="w-full border border-border px-3 py-2 text-sm bg-background outline-none focus:border-foreground transition"
                  />
                </div>
              </div>
            </section>
          </div>

          {/* Right column */}
          <div className="space-y-6">
            {/* Status */}
            <section className="bg-background border border-border p-6 space-y-4">
              <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
                Status
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
              <div className="flex items-center justify-between">
                <Label htmlFor="is_featured" className="text-sm cursor-pointer">
                  Featured
                </Label>
                <Switch
                  id="is_featured"
                  checked={form.is_featured}
                  onCheckedChange={(v) => set("is_featured", v)}
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

            {/* Image */}
            <section className="bg-background border border-border p-6">
              {mode === "new" ? (
                <div className="space-y-2">
                  <p className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground">
                    Image
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Save the collection first, then upload an image from the detail page.
                  </p>
                </div>
              ) : (
                <ImageUpload
                  uploadUrl={uploadUrl}
                  currentImageUrl={form.image_url || null}
                  label="Collection Image"
                  onUploaded={(url) => set("image_url", url)}
                  onRemove={() => {
                    set("image_url", "");
                    api.delete(`/admin/collections/${collection!.id}/image`).catch(() => {});
                  }}
                />
              )}
            </section>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => navigate({ to: "/admin/collections" })}
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
                {mode === "new" ? "Create Collection" : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
