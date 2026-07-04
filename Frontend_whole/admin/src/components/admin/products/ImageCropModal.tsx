import { useEffect, useMemo, useState } from "react";
import Cropper from "react-easy-crop";
import type { Area } from "react-easy-crop";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface SavedCrop {
  x: number;
  y: number;
  width: number;
  height: number;
  zoom: number;
  rotation: number;
}

interface ImageCropModalProps {
  open: boolean;
  imageSrc: string;
  initialCrop?: SavedCrop | null;
  saving?: boolean;
  onCancel: () => void;
  onSave: (crop: SavedCrop) => void;
}

// Storefront product cards, cart, and wishlist all render a 1:1 square —
// crop to that ratio so the saved thumbnail/medium/large line up everywhere.
const ASPECT = 1;

export function ImageCropModal({
  open,
  imageSrc,
  initialCrop,
  saving = false,
  onCancel,
  onSave,
}: ImageCropModalProps) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(initialCrop?.zoom ?? 1);
  const [rotation, setRotation] = useState(initialCrop?.rotation ?? 0);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null);

  // The Cropper only reads `initialCroppedAreaPixels` once, on mount, so this
  // must be a value frozen from props rather than the live `croppedAreaPixels`
  // state (which changes on every drag/zoom).
  const initialAreaPixels = useMemo<Area | undefined>(() => {
    if (!initialCrop) return undefined;
    return {
      x: initialCrop.x,
      y: initialCrop.y,
      width: initialCrop.width,
      height: initialCrop.height,
    };
  }, [initialCrop]);

  // Each image gets an independent crop session — reset the editor whenever a
  // different image is opened so cropping one never leaks into another.
  useEffect(() => {
    if (!open) return;
    setCrop({ x: 0, y: 0 });
    setZoom(initialCrop?.zoom ?? 1);
    setRotation(initialCrop?.rotation ?? 0);
    setCroppedAreaPixels(initialAreaPixels ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, imageSrc]);

  const handleReset = () => {
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setRotation(0);
  };

  const handleSave = () => {
    if (!croppedAreaPixels) return;
    onSave({
      x: croppedAreaPixels.x,
      y: croppedAreaPixels.y,
      width: croppedAreaPixels.width,
      height: croppedAreaPixels.height,
      zoom,
      rotation,
    });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !saving && onCancel()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Crop image</DialogTitle>
        </DialogHeader>

        <div className="relative w-full aspect-square bg-secondary overflow-hidden rounded-sm">
          <Cropper
            image={imageSrc}
            crop={crop}
            zoom={zoom}
            rotation={rotation}
            aspect={ASPECT}
            objectFit="contain"
            zoomWithScroll
            restrictPosition={false}
            initialCroppedAreaPixels={initialAreaPixels}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onRotationChange={setRotation}
            onCropComplete={(_area, areaPixels) => setCroppedAreaPixels(areaPixels)}
          />
        </div>

        <div className="flex flex-col gap-3 pt-1">
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground w-14 shrink-0">Zoom</span>
            <Slider
              min={1}
              max={5}
              step={0.05}
              value={[zoom]}
              onValueChange={([v]) => setZoom(v)}
              disabled={saving}
            />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground w-14 shrink-0">Rotate</span>
            <Slider
              min={-180}
              max={180}
              step={1}
              value={[rotation]}
              onValueChange={([v]) => setRotation(v)}
              disabled={saving}
            />
          </div>
        </div>

        <DialogFooter className="flex-row items-center justify-between sm:justify-between gap-2 pt-2">
          <Button type="button" variant="ghost" size="sm" onClick={handleReset} disabled={saving}>
            <RotateCcw className="size-3.5 mr-1.5" />
            Reset
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleSave}
              disabled={saving || !croppedAreaPixels}
            >
              {saving ? "Saving…" : "Save Crop"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
