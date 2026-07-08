import type { CropPreset } from "@hadha/shared-types";
import { PRESET_REGISTRY as BUNDLED_PRESET_REGISTRY } from "@hadha/shared-types";

/** Raw shape of Backend/app/modules/media/schemas.py's PresetOut (snake_case, as FastAPI serializes it). */
interface PresetOutRaw {
  id: string;
  label: string;
  shape: CropPreset["shape"];
  mask_svg: string | null;
  aspect_ratio: Record<string, number | null>;
  safe_area: { top: number; right: number; bottom: number; left: number };
  min_resolution: Record<string, { width: number; height: number }>;
  max_zoom: number;
  rotation: { allowed: CropPreset["rotation"]["allowed"]; min_degrees: number; max_degrees: number; step_degrees: number };
  breakpoints: CropPreset["breakpoints"];
  output_variants: { name: string; width: number; height: number; dprs: number[]; format: "webp" | "png" }[];
  storage_rules: {
    folder: string;
    max_file_mb: number;
    allowed_mime: string[];
    strict_bounds: boolean;
  };
  reference_ui: string;
}

function mapPresetOut(raw: PresetOutRaw): CropPreset {
  return {
    id: raw.id,
    label: raw.label,
    shape: raw.shape,
    maskSvg: raw.mask_svg,
    aspectRatio: raw.aspect_ratio as CropPreset["aspectRatio"],
    safeArea: raw.safe_area,
    minResolution: raw.min_resolution as CropPreset["minResolution"],
    maxZoom: raw.max_zoom,
    rotation: {
      allowed: raw.rotation.allowed,
      minDegrees: raw.rotation.min_degrees,
      maxDegrees: raw.rotation.max_degrees,
      stepDegrees: raw.rotation.step_degrees,
    },
    breakpoints: raw.breakpoints,
    outputVariants: raw.output_variants,
    storageRules: {
      folder: raw.storage_rules.folder,
      maxFileMb: raw.storage_rules.max_file_mb,
      allowedMime: raw.storage_rules.allowed_mime,
      strictBounds: raw.storage_rules.strict_bounds,
    },
    referenceUi: raw.reference_ui,
  };
}

/**
 * Fetches the live preset registry from GET /admin/media/presets so the
 * frontend never has to hand-keep its bundled copy in sync — falls back to
 * the bundled `PRESET_REGISTRY` (imagePresets.ts) if the request fails,
 * so the editor still works offline/in Storybook/before the backend is up.
 */
export async function fetchPresets(
  apiGet: (path: string) => Promise<PresetOutRaw[]>,
): Promise<Record<string, CropPreset>> {
  try {
    const list = await apiGet("/admin/media/presets");
    return Object.fromEntries(list.map(mapPresetOut).map((p) => [p.id, p]));
  } catch {
    return BUNDLED_PRESET_REGISTRY;
  }
}

let cache: Record<string, CropPreset> | null = null;

/**
 * Cached accessor — call `primePresetCache` once (e.g. app bootstrap) if you
 * want live-backend presets; otherwise every call transparently falls back
 * to the bundled registry.
 */
export function getCachedPreset(presetId: string): CropPreset {
  const registry = cache ?? BUNDLED_PRESET_REGISTRY;
  const preset = registry[presetId];
  if (!preset) {
    throw new Error(`Unknown crop preset: ${presetId}`);
  }
  return preset;
}

export function primePresetCache(registry: Record<string, CropPreset>): void {
  cache = registry;
}
