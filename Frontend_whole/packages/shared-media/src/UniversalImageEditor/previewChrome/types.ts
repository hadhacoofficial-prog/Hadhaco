import type { BreakpointCropGeometry } from "@hadha/shared-types";

export interface PreviewChromeProps {
  /** The untouched original image src — null until the image has loaded. */
  imageSrc: string | null;
  naturalWidth: number;
  naturalHeight: number;
  /** Undefined until this breakpoint's crop has been initialized. */
  geometry: BreakpointCropGeometry | undefined;
}
