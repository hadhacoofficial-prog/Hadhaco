import { useCallback, useState } from "react";
import { Crop as CropIcon, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import {
  UniversalImageEditor,
  uploadImage,
  cropImage,
  getImage,
  toImageBundle,
  type SaveIntent,
  type UniversalImageEditorSaveResult,
} from "@hadha/shared-media";
import { PRESET_REGISTRY } from "@hadha/shared-types";
import type { Breakpoint, BreakpointCropGeometry, ImageBundle } from "@hadha/shared-types";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { toUserMessage } from "@/lib/api/errors";

const HERO_PRESET = PRESET_REGISTRY.hero;

/** Mirrors ProductForm's parseStoredCrops — turns ImageOut's stored
 * metadata.crops back into the shape UniversalImageEditor seeds itself
 * from, so re-opening the editor restores the admin's earlier desktop/
 * mobile framing instead of resetting to a centered default. */
function parseStoredHeroCrops(
  metadataCrops: unknown,
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
  for (const bp of HERO_PRESET.breakpoints) {
    const c = crops[bp];
    if (!c) continue;
    result[bp] = {
      aspectRatio: HERO_PRESET.aspectRatio[bp] ?? null,
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
  bundle?: ImageBundle;
  /** Legacy desktop_image_url, shown as a read-only preview when this slide
   * hasn't been migrated to the crop pipeline yet. */
  legacyDesktopUrl?: string;
  onBundleChange: (bundle: ImageBundle) => void;
}

/**
 * Desktop + mobile crop for one hero slide, via the Universal Responsive
 * Image System's "hero" preset — replaces the old separate desktop/tablet/
 * mobile URL fields with a single upload that's cropped per breakpoint and
 * always renders the correctly-cropped mobile frame (no more a stale
 * mobile_image_url silently overriding the desktop image on phones).
 */
export function HeroImageField({
  slideId,
  bundle,
  legacyDesktopUrl,
  onBundleChange,
}: HeroImageFieldProps) {
  const isSaved = !slideId.startsWith("__");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingExisting, setLoadingExisting] = useState(false);
  const [existingImageSrc, setExistingImageSrc] = useState<string | undefined>(undefined);
  const [initialCrops, setInitialCrops] = useState<
    Partial<Record<Breakpoint, BreakpointCropGeometry>> | undefined
  >(undefined);

  const thumbUrl =
    bundle?.variants.find((v) => v.breakpoint === "desktop")?.url ?? legacyDesktopUrl ?? "";

  const openEditor = useCallback(async () => {
    if (!isSaved) return;
    if (bundle?.imageId) {
      setLoadingExisting(true);
      try {
        const raw = await getImage(bundle.imageId);
        setExistingImageSrc(raw.original_url);
        setInitialCrops(parseStoredHeroCrops(raw.metadata.crops));
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
  }, [isSaved, bundle?.imageId]);

  const handleSave = useCallback(
    async ({ file, geometry }: UniversalImageEditorSaveResult, intent: SaveIntent) => {
      setSaving(true);
      try {
        let raw;
        if (file) {
          const uploaded = await uploadImage({
            presetId: "hero",
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
        toast.success("Hero image saved.");
        if (intent === "save") setOpen(false);
      } catch (e) {
        toast.error(toUserMessage(e as Error));
      } finally {
        setSaving(false);
      }
    },
    [bundle?.imageId, onBundleChange, slideId],
  );

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
        Hero image (desktop + mobile crop)
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
          Save this slide (Save Draft) once to enable the desktop/mobile crop editor.
        </p>
      )}

      <UniversalImageEditor
        open={open}
        onOpenChange={setOpen}
        preset={HERO_PRESET}
        existingImageSrc={existingImageSrc}
        initialCrops={initialCrops}
        saving={saving}
        onCancel={() => setOpen(false)}
        onSave={handleSave}
      />
    </div>
  );
}
