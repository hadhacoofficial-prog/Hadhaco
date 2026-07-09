import type { Breakpoint, BreakpointCropGeometry, CropPreset } from "@hadha/shared-types";
import { PreviewFrame } from "./PreviewFrame";

interface RightPreviewPanelProps {
  preset: CropPreset;
  imageElement: HTMLImageElement | null;
  crops: Partial<Record<Breakpoint, BreakpointCropGeometry>> | undefined;
}

/** Compact live preview column — one real-UI-shaped preview per breakpoint
 * the preset crops. Toggleable from the top bar rather than permanently
 * reserved space, since it's a check, not an editing surface. */
export function RightPreviewPanel({ preset, imageElement, crops }: RightPreviewPanelProps) {
  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Live preview
      </p>
      {preset.breakpoints.map((bp) => (
        <PreviewFrame
          key={bp}
          referenceUi={preset.referenceUi}
          shape={preset.shape}
          breakpoint={bp}
          imageSrc={imageElement?.src ?? null}
          naturalWidth={imageElement?.naturalWidth ?? 0}
          naturalHeight={imageElement?.naturalHeight ?? 0}
          geometry={crops?.[bp]}
        />
      ))}
    </div>
  );
}
