import { useCallback, useState } from "react";
import type { Breakpoint, BreakpointCropGeometry, CropGeometry, CropPreset } from "@hadha/shared-types";
import { defaultCropBox } from "../cropMath";

function seedGeometry(preset: CropPreset, imageWidth: number, imageHeight: number): CropGeometry {
  const crops: CropGeometry["crops"] = {};
  for (const bp of preset.breakpoints) {
    const aspect = preset.aspectRatio[bp] ?? null;
    crops[bp] = {
      aspectRatio: aspect,
      box: defaultCropBox(imageWidth, imageHeight, aspect),
      zoom: 1,
      pan: { x: 0, y: 0 },
      rotation: 0,
    };
  }
  return {
    presetId: preset.id,
    focusPoint: { x: 0.5, y: 0.5 },
    crops,
  };
}

/**
 * Owns the per-breakpoint crop state for one UniversalImageEditor session.
 * Local component state only — no global store, matching the architecture
 * doc's §11 guidance that the editor is self-contained.
 */
export function useCropGeometry(preset: CropPreset) {
  const [geometry, setGeometry] = useState<CropGeometry | null>(null);
  const [activeBreakpoint, setActiveBreakpoint] = useState<Breakpoint>(preset.breakpoints[0]);

  const initialize = useCallback(
    (
      imageWidth: number,
      imageHeight: number,
      initialCrops?: Partial<Record<Breakpoint, BreakpointCropGeometry>>,
    ) => {
      const seeded = seedGeometry(preset, imageWidth, imageHeight);
      if (initialCrops) {
        for (const bp of Object.keys(initialCrops) as Breakpoint[]) {
          const override = initialCrops[bp];
          if (override) seeded.crops[bp] = override;
        }
      }
      setGeometry(seeded);
      setActiveBreakpoint(preset.breakpoints[0]);
    },
    [preset],
  );

  const updateBreakpoint = useCallback(
    (breakpoint: Breakpoint, next: BreakpointCropGeometry) => {
      setGeometry((prev) => (prev ? { ...prev, crops: { ...prev.crops, [breakpoint]: next } } : prev));
    },
    [],
  );

  const copyFromBreakpoint = useCallback((source: Breakpoint, target: Breakpoint) => {
    setGeometry((prev) => {
      if (!prev) return prev;
      const sourceGeometry = prev.crops[source];
      if (!sourceGeometry) return prev;
      const targetAspect = prev.crops[target]?.aspectRatio ?? sourceGeometry.aspectRatio;
      return {
        ...prev,
        crops: { ...prev.crops, [target]: { ...sourceGeometry, aspectRatio: targetAspect } },
      };
    });
  }, []);

  const reset = useCallback(() => setGeometry(null), []);

  return {
    geometry,
    activeBreakpoint,
    setActiveBreakpoint,
    initialize,
    updateBreakpoint,
    copyFromBreakpoint,
    reset,
  };
}
