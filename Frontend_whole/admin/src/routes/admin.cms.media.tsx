import { useRef, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Image, Loader2, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";

import { useMediaList, useUploadMedia, useDeleteMedia } from "@/hooks/cms/useMedia";
import { toUserMessage } from "@/lib/api/errors";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import type { CmsMedia } from "@/types/cms";

export const Route = createFileRoute("/admin/cms/media")({
  component: MediaLibrary,
});

function MediaLibrary() {
  const [page, setPage] = useState(1);
  const [folder, setFolder] = useState<string | undefined>(undefined);
  const [mimeFilter, setMimeFilter] = useState<string | undefined>(undefined);
  const [selected, setSelected] = useState<CmsMedia | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useMediaList({ page, page_size: 48, folder, mime_type: mimeFilter });
  const uploadMutation = useUploadMedia();
  const deleteMutation = useDeleteMedia();

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;

  function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadMutation.mutate(
      { file, folder: folder || "/" },
      {
        onSuccess: (media) => {
          toast.success("Uploaded: " + media.original_filename);
          setPage(1);
        },
        onError: (err) => toast.error(toUserMessage(err)),
      },
    );
    e.target.value = "";
  }

  function handleDelete(media: CmsMedia) {
    if (!confirm(`Delete "${media.original_filename}"? This cannot be undone.`)) return;
    deleteMutation.mutate(media.id, {
      onSuccess: () => {
        toast.success("Deleted.");
        if (selected?.id === media.id) setSelected(null);
      },
      onError: (e) => toast.error(toUserMessage(e)),
    });
  }

  function copyUrl(url: string) {
    navigator.clipboard.writeText(url).then(() => toast.success("URL copied!"));
  }

  return (
    <div className="max-w-6xl">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
            <Link to="/admin/cms" className="hover:text-foreground flex items-center gap-1">
              <ArrowLeft className="size-3.5" />
              CMS
            </Link>
            <span>/</span>
            <span className="text-foreground font-medium">Media Library</span>
          </nav>
          <h1 className="font-display text-3xl">Media Library</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {total} file{total !== 1 ? "s" : ""}
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <input
            ref={fileRef}
            type="file"
            accept="image/*,video/*"
            className="hidden"
            onChange={handleUpload}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploadMutation.isPending}
            aria-busy={uploadMutation.isPending}
            className="inline-flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 text-xs tracking-[0.18em] uppercase hover:bg-primary/90 disabled:opacity-60 transition"
          >
            {uploadMutation.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Upload className="size-3.5" />
            )}
            {uploadMutation.isPending ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 text-xs">
        {["all", "image", "video"].map((type) => {
          const active = type === "all" ? !mimeFilter : mimeFilter === type;
          return (
            <button
              key={type}
              onClick={() => setMimeFilter(type === "all" ? undefined : type)}
              className={`px-3 py-1.5 border transition ${
                active
                  ? "border-primary text-primary"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </button>
          );
        })}
      </div>

      <div className="flex gap-4">
        {/* Grid */}
        <div className="flex-1 min-w-0">
          {isLoading && (
            <div className="grid grid-cols-4 md:grid-cols-6 gap-2">
              {Array.from({ length: 24 }).map((_, i) => (
                <div key={i} className="aspect-square bg-muted animate-pulse rounded" />
              ))}
            </div>
          )}

          {!isLoading && items.length === 0 && (
            <div className="text-center py-20 text-muted-foreground">
              <Image className="size-8 mx-auto mb-3 opacity-40" />
              <p className="text-sm">No media files yet. Upload your first file.</p>
            </div>
          )}

          {!isLoading && items.length > 0 && (
            <div className="grid grid-cols-4 md:grid-cols-6 gap-2">
              {items.map((m) => (
                <MediaTile
                  key={m.id}
                  media={m}
                  isSelected={selected?.id === m.id}
                  onClick={() => setSelected((prev) => (prev?.id === m.id ? null : m))}
                />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6 text-sm">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 border border-border disabled:opacity-40 hover:bg-muted transition"
              >
                Prev
              </button>
              <span className="text-muted-foreground">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 border border-border disabled:opacity-40 hover:bg-muted transition"
              >
                Next
              </button>
            </div>
          )}
        </div>

        {/* Side panel */}
        {selected && (
          <aside className="w-64 shrink-0 border border-border p-4 self-start">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
                Details
              </span>
              <button onClick={() => setSelected(null)}>
                <X className="size-4" />
              </button>
            </div>

            <div className="aspect-square border border-border overflow-hidden mb-3 bg-muted">
              {selected.mime_type.startsWith("image/") ? (
                <ImageWithFallback
                  src={selected.thumbnail_url || selected.cdn_url}
                  alt={selected.alt_text ?? ""}
                  className="w-full h-full"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
                  Video
                </div>
              )}
            </div>

            <p className="text-sm font-medium truncate" title={selected.original_filename}>
              {selected.original_filename}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {(selected.file_size / 1024).toFixed(0)} KB
              {selected.width ? ` · ${selected.width}×${selected.height}` : ""}
            </p>
            <p className="text-xs text-muted-foreground">{selected.mime_type}</p>
            <p className="text-xs text-muted-foreground">
              {new Date(selected.created_at).toLocaleDateString()}
            </p>

            {selected.alt_text && (
              <p className="text-xs text-muted-foreground mt-2">Alt: {selected.alt_text}</p>
            )}

            <div className="mt-3 space-y-2">
              <button
                onClick={() => copyUrl(selected.cdn_url)}
                className="w-full text-xs border border-border py-1.5 hover:bg-muted transition"
              >
                Copy URL
              </button>
              {selected.thumbnail_url && (
                <button
                  onClick={() => copyUrl(selected.thumbnail_url!)}
                  className="w-full text-xs border border-border py-1.5 hover:bg-muted transition"
                >
                  Copy thumbnail URL
                </button>
              )}
              <button
                onClick={() => handleDelete(selected)}
                disabled={deleteMutation.isPending}
                aria-busy={deleteMutation.isPending}
                className="w-full inline-flex items-center justify-center gap-2 text-xs border border-destructive text-destructive py-1.5 hover:bg-destructive hover:text-destructive-foreground disabled:opacity-50 transition"
              >
                {deleteMutation.isPending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Trash2 className="size-3.5" />
                )}
                {deleteMutation.isPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function MediaTile({
  media,
  isSelected,
  onClick,
}: {
  media: CmsMedia;
  isSelected: boolean;
  onClick: () => void;
}) {
  const isImage = media.mime_type.startsWith("image/");
  return (
    <button
      onClick={onClick}
      className={`relative aspect-square border overflow-hidden transition group ${
        isSelected ? "border-primary ring-1 ring-primary" : "border-border hover:border-foreground"
      }`}
    >
      {isImage ? (
        <ImageWithFallback
          src={media.thumbnail_url || media.cdn_url}
          alt={media.alt_text ?? ""}
          className="w-full h-full"
        />
      ) : (
        <div className="w-full h-full bg-muted flex items-center justify-center text-[10px] text-muted-foreground uppercase tracking-widest">
          Video
        </div>
      )}
      <div className="absolute inset-0 bg-primary/0 group-hover:bg-primary/10 transition-colors" />
    </button>
  );
}
