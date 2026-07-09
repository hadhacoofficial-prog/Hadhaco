import { useMemo } from "react";
import type { Ref } from "react";
import Cropper from "react-easy-crop";
import type { Area } from "react-easy-crop";
import type { BreakpointCropGeometry, CropPreset } from "@hadha/shared-types";
import { MiniNavigator } from "./MiniNavigator";
import { SafeAreaOverlay } from "./SafeAreaOverlay";
import { ShapeMaskOverlay } from "./ShapeMaskOverlay";

interface CropCanvasProps {
  imageSrc: string;
  preset: CropPreset;
  aspect: number | undefined;
  geometry: BreakpointCropGeometry;
  imageNaturalWidth: number;
  imageNaturalHeight: number;
  onChange: (geometry: BreakpointCropGeometry) => void;
  onInteractionEnd: () => void;
  showGrid: boolean;
  showSafeArea: boolean;
  containerRef: Ref<HTMLDivElement>;
}

/**
 * The primary workspace — a maximized interactive crop/zoom/pan/rotate
 * surface for a single breakpoint, edge to edge with no surrounding chrome.
 * Wraps react-easy-crop (drag-to-pan and wheel-to-zoom are built in) and
 * layers the shape mask, optional safe-area guide, and a corner navigator
 * once zoomed in. Every other control (grid/safe-area toggles, zoom,
 * rotation, fit/100%, undo/redo, save) lives in the single sticky bottom
 * toolbar, not scattered around the canvas.
 */
export function CropCanvas({
  imageSrc,
  preset,
  aspect,
  geometry,
  imageNaturalWidth,
  imageNaturalHeight,
  onChange,
  onInteractionEnd,
  showGrid,
  showSafeArea,
  containerRef,
}: CropCanvasProps) {
  const initialAreaPixels = useMemo<Area | undefined>(() => {
    if (!geometry.box.width || !geometry.box.height) return undefined;
    return {
      x: geometry.box.x,
      y: geometry.box.y,
      width: geometry.box.width,
      height: geometry.box.height,
    };
  }, [geometry.box.x, geometry.box.y, geometry.box.width, geometry.box.height]);

  return (
    <div ref={containerRef} className="relative h-full min-h-[420px] w-full bg-neutral-950">
      <Cropper
        image={imageSrc}
        crop={geometry.pan}
        zoom={geometry.zoom}
        minZoom={1}
        maxZoom={preset.maxZoom}
        rotation={geometry.rotation}
        aspect={aspect}
        objectFit="contain"
        zoomWithScroll
        showGrid={showGrid}
        restrictPosition={false}
        initialCroppedAreaPixels={initialAreaPixels}
        onCropChange={(pan) => onChange({ ...geometry, pan })}
        onZoomChange={(zoom) => onChange({ ...geometry, zoom })}
        onRotationChange={(rotation) => onChange({ ...geometry, rotation })}
        onInteractionEnd={onInteractionEnd}
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
      {showSafeArea && <SafeAreaOverlay safeArea={preset.safeArea} />}
      {geometry.zoom > 1.01 && (
        <MiniNavigator
          imageSrc={imageSrc}
          naturalWidth={imageNaturalWidth}
          naturalHeight={imageNaturalHeight}
          box={geometry.box}
        />
      )}
    </div>
  );
}
