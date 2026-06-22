import { useRef, useState } from "react";
import { Upload, X, ImageIcon, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";

interface ImageUploadProps {
  uploadUrl: string;
  currentImageUrl?: string | null;
  onUploaded: (url: string) => void;
  onRemove?: () => void;
  label?: string;
  className?: string;
}

export function ImageUpload({
  uploadUrl,
  currentImageUrl,
  onUploaded,
  onRemove,
  label = "Image",
  className = "",
}: ImageUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(currentImageUrl ?? null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  async function handleFile(file: File) {
    if (!file.type.match(/^image\/(jpeg|png|webp)$/)) {
      toast.error("Only JPG, PNG, or WebP images are supported.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error("Image must be under 10 MB.");
      return;
    }

    const localPreview = URL.createObjectURL(file);
    setPreview(localPreview);

    const form = new FormData();
    form.append("file", file);

    setUploading(true);
    setProgress(10);

    try {
      const simulateProgress = setInterval(() => {
        setProgress((p) => Math.min(p + 15, 85));
      }, 200);

      const res = await api.upload<{ url: string }>(uploadUrl, form);
      clearInterval(simulateProgress);
      setProgress(100);
      onUploaded(res.url);
      setTimeout(() => setProgress(0), 500);
    } catch (e) {
      setPreview(currentImageUrl ?? null);
      toast.error(toUserMessage(e));
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function handleRemove() {
    setPreview(null);
    if (inputRef.current) inputRef.current.value = "";
    onRemove?.();
  }

  return (
    <div className={`space-y-2 ${className}`}>
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-[0.15em]">
        {label}
      </p>

      {preview ? (
        <div className="relative group w-full aspect-video bg-secondary overflow-hidden border border-border">
          <img
            src={preview}
            alt="Preview"
            className="w-full h-full object-cover"
          />
          {uploading && (
            <div className="absolute inset-0 bg-foreground/60 flex flex-col items-center justify-center gap-2">
              <Loader2 className="size-6 animate-spin text-background" />
              <div className="w-32 h-1 bg-background/30 rounded-full overflow-hidden">
                <div
                  className="h-full bg-background transition-all duration-200"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}
          {!uploading && (
            <div className="absolute inset-0 bg-foreground/0 group-hover:bg-foreground/40 transition-all flex items-center justify-center opacity-0 group-hover:opacity-100">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  className="bg-background text-foreground text-xs px-3 py-1.5 hover:bg-secondary transition"
                >
                  Change
                </button>
                {onRemove && (
                  <button
                    type="button"
                    onClick={handleRemove}
                    className="bg-destructive text-destructive-foreground text-xs px-3 py-1.5 hover:opacity-90 transition"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => inputRef.current?.click()}
          className="w-full aspect-video border-2 border-dashed border-border bg-secondary/40 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-foreground/40 transition-colors"
        >
          {uploading ? (
            <>
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
              <p className="text-xs text-muted-foreground">Uploading…</p>
            </>
          ) : (
            <>
              <Upload className="size-5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">
                Drop image or <span className="underline">browse</span>
              </p>
              <p className="text-[10px] text-muted-foreground/60">JPG, PNG, WebP · max 10 MB</p>
            </>
          )}
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
    </div>
  );
}
