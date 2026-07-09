import { Info } from "lucide-react";
import { Button } from "@hadha/shared-ui/ui/button";
import { Input } from "@hadha/shared-ui/ui/input";
import { Label } from "@hadha/shared-ui/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@hadha/shared-ui/ui/popover";
import type { Breakpoint, CropPreset } from "@hadha/shared-types";

interface ImageInfoPopoverProps {
  preset: CropPreset;
  imageWidth: number;
  imageHeight: number;
  activeBreakpoint: Breakpoint;
  /** Only rendered once an image already exists server-side — a brand-new
   * upload has no image id to PATCH alt text onto yet. */
  altText?: string;
  onAltTextChange?: (value: string) => void;
  onAltTextCommit?: () => void;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}

/** Image metadata (dimensions, preset, shape, aspect ratio) — useful once in
 * a while to sanity-check, not something worth a permanently-visible panel.
 * Collapsed into an on-demand popover instead. */
export function ImageInfoPopover({
  preset,
  imageWidth,
  imageHeight,
  activeBreakpoint,
  altText,
  onAltTextChange,
  onAltTextCommit,
}: ImageInfoPopoverProps) {
  const activeAspect = preset.aspectRatio[activeBreakpoint];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon" className="size-8" title="Image info">
          <Info className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 space-y-2 p-3">
        <Row label="Original size" value={`${imageWidth} × ${imageHeight}px`} />
        <Row label="Preset" value={preset.label} />
        <Row label="Shape" value={preset.shape.replace("_", " ")} />
        <Row
          label="Aspect ratio"
          value={activeAspect ? activeAspect.toFixed(2) + " : 1" : "Free"}
        />
        <Row label="Max zoom" value={`${preset.maxZoom}×`} />
        {onAltTextChange && (
          <div className="space-y-1 pt-1">
            <Label htmlFor="image-alt-text" className="text-xs text-muted-foreground">
              Alt text
            </Label>
            <Input
              id="image-alt-text"
              value={altText ?? ""}
              maxLength={500}
              placeholder="Describe this image…"
              className="h-7 text-xs"
              onChange={(e) => onAltTextChange(e.target.value)}
              onBlur={onAltTextCommit}
            />
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
