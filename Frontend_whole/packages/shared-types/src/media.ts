/**
 * Universal Image System contracts — TS mirror of
 * Backend/app/modules/media/preset_registry.py's CropPreset schema.
 *
 * See docs/architecture/Universal_Responsive_Image_System_Design.md §5-§6, §13.
 * Kept in lockstep with the Python registry by hand for now; a build-time
 * codegen step (Python model -> JSON Schema -> TS types) is a Phase 0
 * tooling follow-up noted in the design doc, not yet implemented.
 */

export type ShapeType =
  | "rectangle"
  | "square"
  | "circle"
  | "rounded_rect"
  | "contain"
  | "cover"
  | "custom_mask";

export type Breakpoint = "desktop" | "tablet" | "mobile" | "all";

export type RotationMode = "none" | "90_step" | "free";

export interface Resolution {
  width: number;
  height: number;
}

export interface SafeArea {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface RotationPolicy {
  allowed: RotationMode;
  minDegrees: number;
  maxDegrees: number;
  stepDegrees: number;
}

export interface VariantSpec {
  name: string;
  width: number;
  height: number;
  dprs: number[];
  format: "webp" | "png";
}

export interface StorageRules {
  folder: string;
  maxFileMb: number;
  allowedMime: string[];
  strictBounds: boolean;
}

export interface CropPreset {
  id: string;
  label: string;
  shape: ShapeType;
  maskSvg: string | null;
  aspectRatio: Partial<Record<Breakpoint, number | null>>;
  safeArea: SafeArea;
  minResolution: Partial<Record<Breakpoint, Resolution>>;
  maxZoom: number;
  rotation: RotationPolicy;
  breakpoints: Breakpoint[];
  outputVariants: VariantSpec[];
  storageRules: StorageRules;
  /** Selects which mini-layout in previewChrome/ renders this preset's PreviewFrame. */
  referenceUi: string;
}

/** Crop state for a single breakpoint, in the original image's own pixel space. */
export interface CropBoxGeometry {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface BreakpointCropGeometry {
  aspectRatio: number | null;
  box: CropBoxGeometry;
  zoom: number;
  pan: { x: number; y: number };
  rotation: number;
}

export interface CropGeometry {
  presetId: string;
  focusPoint: { x: number; y: number };
  crops: Partial<Record<Breakpoint, BreakpointCropGeometry>>;
}

/** Slimmed projection returned by owner-entity API responses (architecture doc §13). */
export interface ImageBundleVariant {
  breakpoint: Breakpoint;
  dpr: number;
  url: string;
  width: number;
  height: number;
}

export interface ImageBundle {
  imageId: string;
  altText: string | null;
  focusPoint: { x: number; y: number };
  variants: ImageBundleVariant[];
}
