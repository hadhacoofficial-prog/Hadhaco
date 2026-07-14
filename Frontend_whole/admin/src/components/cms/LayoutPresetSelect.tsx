import { type HeroLayoutPreset } from "@/types/cms";

interface LayoutPresetSelectProps {
  label: string;
  value: HeroLayoutPreset;
  onChange: (preset: HeroLayoutPreset) => void;
}

interface PresetThumbnailProps {
  preset: HeroLayoutPreset;
  isActive: boolean;
  onClick: () => void;
}

function PresetThumbnail({ preset, isActive, onClick }: PresetThumbnailProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col items-center gap-1.5 p-2 rounded-lg border transition-all ${
        isActive
          ? "border-primary/60 bg-primary/5 shadow-sm"
          : "border-border/40 hover:border-border hover:bg-muted/30"
      }`}
    >
      <div className="w-16 h-10 bg-muted/60 rounded-sm overflow-hidden relative border border-border/30">
        <PresetVisual preset={preset} />
      </div>
      <span className="text-[10px] text-foreground/70 leading-tight text-center">
        {PRESET_LABELS[preset]}
      </span>
    </button>
  );
}

function PresetVisual({ preset }: { preset: HeroLayoutPreset }) {
  const lines = (
    <>
      <div className="w-1 h-1 rounded-full bg-muted-foreground/40" />
      <div className="w-8 h-0.5 bg-muted-foreground/30" />
      <div className="w-6 h-0.5 bg-muted-foreground/20" />
    </>
  );

  switch (preset) {
    case "classic-left":
      return (
        <div className="absolute inset-0 flex flex-col items-start justify-center gap-1 pl-1.5">
          {lines}
        </div>
      );
    case "centered-luxury":
      return (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1">
          {lines}
        </div>
      );
    case "editorial":
      return (
        <div className="absolute inset-0 flex flex-col items-start justify-end gap-1 pl-1.5 pb-1">
          {lines}
        </div>
      );
    case "minimal":
      return (
        <div className="absolute inset-0 flex flex-col items-center justify-start gap-1 pt-1">
          {lines}
        </div>
      );
    case "image-focused":
      return (
        <div className="absolute inset-0 flex flex-col items-center justify-end gap-1 pb-1">
          <div className="w-6 h-0.5 bg-muted-foreground/20" />
          <div className="w-8 h-0.5 bg-muted-foreground/30" />
        </div>
      );
    case "split":
      return (
        <div className="absolute inset-0 flex flex-col items-end justify-center gap-1 pr-1.5">
          {lines}
        </div>
      );
  }
}

const PRESET_LABELS: Record<HeroLayoutPreset, string> = {
  "classic-left": "Classic Left",
  "centered-luxury": "Centered",
  editorial: "Editorial",
  minimal: "Minimal",
  "image-focused": "Image Focus",
  split: "Classic Right",
};

export function LayoutPresetSelect({ label, value, onChange }: LayoutPresetSelectProps) {
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </p>
      <div className="grid grid-cols-3 gap-2">
        {(
          [
            "classic-left",
            "centered-luxury",
            "editorial",
            "minimal",
            "image-focused",
            "split",
          ] as const
        ).map((preset) => (
          <PresetThumbnail
            key={preset}
            preset={preset}
            isActive={value === preset}
            onClick={() => onChange(preset)}
          />
        ))}
      </div>
    </div>
  );
}
