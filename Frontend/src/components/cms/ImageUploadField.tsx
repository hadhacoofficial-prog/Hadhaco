import { useRef, useState } from "react";
import { Loader2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import type { CmsMedia } from "@/types/cms";

interface ImageUploadFieldProps {
  label?: string;
  value: string;
  onChange: (url: string) => void;
  accept?: string;
  folder?: string;
  previewHeight?: number;
}

export function ImageUploadField({
  label,
  value,
  onChange,
  accept = "image/*",
  folder = "/cms",
  previewHeight = 100,
}: ImageUploadFieldProps) {
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("folder", folder);
      const result = await api.post<CmsMedia>("/cms/admin/media/upload", { body: fd });
      onChange(result.cdn_url);
      toast.success("Uploaded to CDN.");
    } catch (e) {
      toast.error(toUserMessage(e as Error));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-1.5">
      {label && (
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          {label}
        </p>
      )}

      {value && (
        <div className="relative rounded overflow-hidden border border-border/40 bg-muted/20">
          <img
            src={value}
            alt=""
            style={{ height: previewHeight }}
            className="w-full object-cover"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
          <button
            type="button"
            onClick={() => onChange("")}
            className="absolute top-1.5 right-1.5 size-5 bg-background/80 rounded-full flex items-center justify-center hover:bg-background border border-border/40 transition-colors"
          >
            <X className="size-3" />
          </button>
        </div>
      )}

      <div className="flex gap-1.5">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="https://cdn… or upload ↗"
          className="flex-1 border border-border/60 bg-background/80 px-2.5 py-1.5 text-xs outline-none focus:border-primary transition-colors rounded-sm placeholder:text-muted-foreground/40"
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="shrink-0 px-2.5 py-1.5 border border-border/60 rounded-sm hover:bg-muted transition-colors disabled:opacity-50 text-muted-foreground text-xs flex items-center gap-1"
          title="Upload from computer"
        >
          {uploading ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
          {uploading ? "Uploading" : "Upload"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}
