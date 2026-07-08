import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@hadha/shared-ui/ui/button";
import type { Breakpoint, BreakpointCropGeometry, CropGeometry, CropPreset } from "@hadha/shared-types";
import { BreakpointTabs } from "./BreakpointTabs";
import { CropCanvas } from "./CropCanvas";
import { PreviewFrame } from "./PreviewFrame";
import { useCropGeometry } from "./useCropGeometry";

export interface UniversalImageEditorSaveResult {
  /** Null when re-editing an existing image's crop with no new file chosen —
   * the caller should PATCH the new geometry onto the existing image id
   * rather than uploading, since the server always re-derives from the
   * already-stored original anyway (architecture doc §4). */
  file: File | null;
  geometry: CropGeometry;
}

export interface UniversalImageEditorProps {
  preset: CropPreset;
  /** Existing image URL to start from (re-edit flow); omit for a fresh upload. */
  existingImageSrc?: string;
  /** Seeds the crop editor from a previously-saved geometry (re-edit flow) —
   * without this, re-opening the editor always starts from a fresh centered
   * crop, losing the admin's earlier framing choice. */
  initialCrops?: Partial<Record<Breakpoint, BreakpointCropGeometry>>;
  saving?: boolean;
  onCancel?: () => void;
  onSave: (result: UniversalImageEditorSaveResult) => void | Promise<void>;
}

/**
 * The single upload/crop/preview component every module consumes — driven
 * entirely by *preset*, never by module-specific logic (architecture doc §11,
 * §14). Upload -> per-breakpoint Crop -> simultaneous Preview -> Save.
 */
export function UniversalImageEditor({
  preset,
  existingImageSrc,
  initialCrops,
  saving = false,
  onCancel,
  onSave,
}: UniversalImageEditorProps) {
  const [file, setFile] = useState<File | null>(null);
  const [imageSrc, setImageSrc] = useState<string | null>(existingImageSrc ?? null);
  const [imageElement, setImageElement] = useState<HTMLImageElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { geometry, activeBreakpoint, setActiveBreakpoint, initialize, updateBreakpoint, copyFromBreakpoint } =
    useCropGeometry(preset);

  useEffect(() => {
    if (!imageSrc) return;
    const img = new Image();
    img.onload = () => {
      setImageElement(img);
      // Only seed from the previously-saved crop when we're still showing
      // the original existing image — a freshly-picked replacement file
      // should always start from a fresh centered crop.
      const seedFromExisting = imageSrc === existingImageSrc ? initialCrops : undefined;
      initialize(img.naturalWidth, img.naturalHeight, seedFromExisting);
    };
    img.src = imageSrc;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageSrc]);

  const handleFileSelected = useCallback((selected: File) => {
    setFile(selected);
    setImageSrc(URL.createObjectURL(selected));
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files?.[0];
      if (selected) handleFileSelected(selected);
    },
    [handleFileSelected],
  );

  const handleSave = useCallback(() => {
    if (!geometry) return;
    onSave({ file, geometry });
  }, [file, geometry, onSave]);

  const activeGeometry = geometry?.crops[activeBreakpoint];
  const aspect = activeGeometry?.aspectRatio ?? undefined;

  if (!imageSrc) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 border-2 border-dashed rounded-lg p-10">
        <p className="text-sm text-muted-foreground">
          Upload an image for &ldquo;{preset.label}&rdquo;
        </p>
        <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
          Choose file
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={preset.storageRules.allowedMime.join(",")}
          className="hidden"
          onChange={handleInputChange}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="text-xs text-muted-foreground">
        Preset: <span className="font-medium text-foreground">{preset.label}</span> · Shape:{" "}
        {preset.shape} · Max zoom {preset.maxZoom}x
      </div>

      <BreakpointTabs
        breakpoints={preset.breakpoints}
        active={activeBreakpoint}
        onChange={setActiveBreakpoint}
        onCopyFromDesktop={() => copyFromBreakpoint("desktop", activeBreakpoint)}
      />

      {activeGeometry && (
        <CropCanvas
          imageSrc={imageSrc}
          preset={preset}
          aspect={aspect}
          geometry={activeGeometry}
          onChange={(next) => updateBreakpoint(activeBreakpoint, next)}
        />
      )}

      <div className="flex flex-wrap justify-center gap-4 rounded-md border p-4 bg-muted/30">
        {preset.breakpoints.map((bp) => (
          <PreviewFrame
            key={bp}
            referenceUi={preset.referenceUi}
            breakpoint={bp}
            imageElement={imageElement}
            geometry={geometry?.crops[bp]}
          />
        ))}
      </div>

      <div className="flex items-center justify-between gap-2 pt-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={saving}
        >
          Replace file
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={preset.storageRules.allowedMime.join(",")}
          className="hidden"
          onChange={handleInputChange}
        />
        <div className="flex gap-2">
          {onCancel && (
            <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
          )}
          <Button type="button" size="sm" onClick={handleSave} disabled={saving || !geometry}>
            {saving ? "Saving…" : "Save & Generate Variants"}
          </Button>
        </div>
      </div>
    </div>
  );
}
