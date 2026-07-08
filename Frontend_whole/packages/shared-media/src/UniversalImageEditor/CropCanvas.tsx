import { useMemo } from "react";
import Cropper from "react-easy-crop";
import type { Area } from "react-easy-crop";
import { Slider } from "@hadha/shared-ui/ui/slider";
import type { BreakpointCropGeometry, CropPreset } from "@hadha/shared-types";
import { ShapeMaskOverlay } from "./ShapeMaskOverlay";

interface CropCanvasProps {
  imageSrc: string;
  preset: CropPreset;
  aspect: number | undefined;
  geometry: BreakpointCropGeometry;
  onChange: (geometry: BreakpointCropGeometry) => void;
}

/**
 * The interactive crop/zoom/pan/rotate surface for a single breakpoint.
 * Wraps react-easy-crop (the library already exercised by the pre-Universal
 * ProductForm/ImageCropModal flow) and layers a shape mask preview on top.
 */
export function CropCanvas({ imageSrc, preset, aspect, geometry, onChange }: CropCanvasProps) {
  const initialAreaPixels = useMemo<Area | undefined>(() => {
    if (!geometry.box.width || !geometry.box.height) return undefined;
    return {
      x: geometry.box.x,
      y: geometry.box.y,
      width: geometry.box.width,
      height: geometry.box.height,
    };
  }, [geometry.box.x, geometry.box.y, geometry.box.width, geometry.box.height]);

  const rotationAllowed = preset.rotation.allowed !== "none";

  return (
    <div className="flex flex-col gap-3">
      <div className="relative w-full aspect-square bg-secondary overflow-hidden rounded-sm">
        <Cropper
          image={imageSrc}
          crop={geometry.pan}
          zoom={geometry.zoom}
          rotation={geometry.rotation}
          aspect={aspect}
          objectFit="contain"
          zoomWithScroll
          restrictPosition={false}
          initialCroppedAreaPixels={initialAreaPixels}
          onCropChange={(pan) => onChange({ ...geometry, pan })}
          onZoomChange={(zoom) => onChange({ ...geometry, zoom })}
          onRotationChange={(rotation) => onChange({ ...geometry, rotation })}
          onCropComplete={(_area, areaPixels) =>
            onChange({
              ...geometry,
              box: {
                x: areaPixels.x,
                y: areaPixels.y,
                width: areaPixels.width,
                height: areaPixels.height,
              },
            })
          }
        />
        <ShapeMaskOverlay shape={preset.shape} />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground w-14 shrink-0">Zoom</span>
          <Slider
            min={1}
            max={preset.maxZoom}
            step={0.05}
            value={[geometry.zoom]}
            onValueChange={([v]) => onChange({ ...geometry, zoom: v })}
          />
        </div>
        {rotationAllowed && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground w-14 shrink-0">Rotate</span>
            <Slider
              min={preset.rotation.minDegrees}
              max={preset.rotation.maxDegrees}
              step={preset.rotation.stepDegrees}
              value={[geometry.rotation]}
              onValueChange={([v]) => onChange({ ...geometry, rotation: v })}
            />
          </div>
        )}
      </div>
    </div>
  );
}
