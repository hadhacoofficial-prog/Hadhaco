import { useCallback, useEffect, useRef, useState } from "react";
import { Crop as CropIcon, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import {
  UniversalImageEditor,
  uploadImage,
  cropImage,
  getImage,
  pollImageUntilReady,
  toImageBundle,
  type SaveIntent,
  type UniversalImageEditorSaveResult,
} from "@hadha/shared-media";
import { PRESET_REGISTRY } from "@hadha/shared-types";
import type { Breakpoint, BreakpointCropGeometry, ImageBundle } from "@hadha/shared-types";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { toUserMessage } from "@/lib/api/errors";

/** Mirrors ProductForm's parseStoredCrops — turns ImageOut's stored
 * metadata.crops back into the shape UniversalImageEditor seeds itself
 * from, so re-opening the editor restores the admin's earlier framing
 * instead of resetting to a centered default. Generic over the preset's own
 * breakpoint list (each hero preset here has exactly one). */
function parseStoredCrops(
  metadataCrops: unknown,
  breakpoints: Breakpoint[],
  aspectRatio: Partial<Record<Breakpoint, number | null>>,
): Partial<Record<Breakpoint, BreakpointCropGeometry>> | undefined {
  const crops = metadataCrops as
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
  for (const bp of breakpoints) {
    const c = crops[bp];
    if (!c) continue;
    result[bp] = {
      aspectRatio: aspectRatio[bp] ?? null,
      box: c.box,
      zoom: c.zoom,
      pan: { x: 0, y: 0 },
      rotation: c.rotation,
    };
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

interface HeroImageFieldProps {
  /** The slide's SectionItem id — real once the slide has been saved at
   * least once via "Save Draft", a synthetic "__new_..." id before that. */
  slideId: string;
  label: string;
  presetId: "hero_desktop" | "hero_mobile";
  bundle?: ImageBundle;
  /** Legacy plain-URL value, shown as a read-only preview when this slot
   * hasn't been migrated to the crop pipeline yet. */
  legacyUrl?: string;
  onBundleChange: (bundle: ImageBundle) => void;
}

/**
 * One independent upload + single-frame crop for a hero slide — desktop and
 * mobile are two entirely separate images (often different source photos),
 * each via its own instance of this field and its own Universal Image
 * Editor session, rather than one image cropped two ways.
 */
export function HeroImageField({
  slideId,
  label,
  presetId,
  bundle,
  legacyUrl,
  onBundleChange,
}: HeroImageFieldProps) {
  const preset = PRESET_REGISTRY[presetId];
  const isSaved = !slideId.startsWith("__");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingExisting, setLoadingExisting] = useState(false);
  const [existingImageSrc, setExistingImageSrc] = useState<string | undefined>(undefined);
  const [initialCrops, setInitialCrops] = useState<
    Partial<Record<Breakpoint, BreakpointCropGeometry>> | undefined
  >(undefined);

  const mountedRef = useRef(true);
  useEffect(
    () => () => {
      mountedRef.current = false;
    },
    [],
  );

  const thumbUrl = bundle?.variants[0]?.url ?? legacyUrl ?? "";

  const openEditor = useCallback(async () => {
    if (!isSaved) return;
    if (bundle?.imageId) {
      setLoadingExisting(true);
      try {
        const raw = await getImage(bundle.imageId);
        setExistingImageSrc(raw.original_url);
        setInitialCrops(
          parseStoredCrops(raw.metadata.crops, preset.breakpoints, preset.aspectRatio),
        );
      } catch (e) {
        toast.error(toUserMessage(e as Error));
        return;
      } finally {
        setLoadingExisting(false);
      }
    } else {
      setExistingImageSrc(undefined);
      setInitialCrops(undefined);
    }
    setOpen(true);
  }, [isSaved, bundle?.imageId, preset]);

  const handleSave = useCallback(
    async ({ file, geometry }: UniversalImageEditorSaveResult, intent: SaveIntent) => {
      setSaving(true);
      try {
        let raw;
        if (file) {
          const uploaded = await uploadImage({
            presetId,
            file,
            ownerType: "cms_section_item",
            ownerId: slideId,
          });
          raw = await cropImage(uploaded.id, geometry);
        } else if (bundle?.imageId) {
          raw = await cropImage(bundle.imageId, geometry);
        } else {
          return;
        }
        onBundleChange(toImageBundle(raw));
        toast.success(`${label} saved.`);
        if (intent === "save") setOpen(false);
        // Crop/upload return as soon as the geometry is persisted — the
        // actual variant files are produced by a background worker, so
        // right after saving, toImageBundle()'s "ready"-only filter yields
        // zero variants and no thumbnail shows. Poll until the worker
        // finishes, then swap in the real thumbnail.
        if (raw.status !== "ready") {
          pollImageUntilReady(raw.id)
            .then((fresh) => {
              if (mountedRef.current) onBundleChange(toImageBundle(fresh));
            })
            .catch(() => {
              // Worker failure/timeout — leave the last-known bundle in
              // place; the admin can reopen the editor to retry/regenerate.
            });
        }
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      } finally {
        setSaving(false);
      }
    },
    [bundle?.imageId, onBundleChange, slideId, presetId, label],
  );

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </p>

      {thumbUrl && (
        <div className="relative rounded overflow-hidden border border-border/40 bg-muted/20">
          <ImageWithFallback
            src={thumbUrl}
            alt=""
            style={{ height: 90 }}
            className="w-full"
            imgClassName="object-cover"
          />
        </div>
      )}

      {isSaved ? (
        <button
          type="button"
          onClick={openEditor}
          disabled={loadingExisting}
          className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 border border-border/60 rounded-sm hover:bg-muted transition-colors disabled:opacity-50 text-muted-foreground text-xs"
        >
          {loadingExisting ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : bundle ? (
            <CropIcon className="size-3.5" />
          ) : (
            <Upload className="size-3.5" />
          )}
          {loadingExisting ? "Loading…" : bundle ? "Edit crop" : "Upload & crop image"}
        </button>
      ) : (
        <p className="text-[10px] text-muted-foreground/60 italic">
          Save this slide (Save Draft) once to enable cropping.
        </p>
      )}

      <UniversalImageEditor
        open={open}
        onOpenChange={setOpen}
        preset={preset}
        existingImageSrc={existingImageSrc}
        initialCrops={initialCrops}
        saving={saving}
        onCancel={() => setOpen(false)}
        onSave={handleSave}
      />
    </div>
  );
}
