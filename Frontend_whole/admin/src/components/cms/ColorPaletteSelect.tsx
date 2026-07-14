import { HERO_PALETTE } from "@/types/cms";
import type { HeroPaletteName } from "@/types/cms";

interface ColorPaletteSelectProps {
  label: string;
  value: HeroPaletteName;
  customValue?: string;
  onChange: (palette: HeroPaletteName, custom?: string) => void;
}

export function ColorPaletteSelect({
  label,
  value,
  customValue,
  onChange,
}: ColorPaletteSelectProps) {
  const palettes = Object.entries(HERO_PALETTE).filter(([k]) => k !== "custom");

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </p>
      <div className="flex items-center gap-2 flex-wrap">
        {palettes.map(([key, entry]) => {
          const name = key as HeroPaletteName;
          const isSelected = value === name;
          return (
            <button
              key={name}
              type="button"
              onClick={() => onChange(name)}
              className={`group relative flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs transition-all ${
                isSelected
                  ? "border-primary/60 bg-primary/5 shadow-sm"
                  : "border-border/40 hover:border-border hover:bg-muted/30"
              }`}
              title={entry.label}
            >
              <span
                className="size-4 rounded-full border border-black/10 shrink-0"
                style={{ backgroundColor: entry.swatch }}
              />
              <span className="text-xs text-foreground/80">{entry.label}</span>
              {isSelected && (
                <span className="absolute -top-1 -right-1 size-3 rounded-full bg-primary flex items-center justify-center">
                  <span className="size-1.5 rounded-full bg-primary-foreground" />
                </span>
              )}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => onChange("custom", customValue ?? "#000000")}
          className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs transition-all ${
            value === "custom"
              ? "border-primary/60 bg-primary/5 shadow-sm"
              : "border-border/40 hover:border-border hover:bg-muted/30"
          }`}
        >
          <span className="text-xs text-foreground/60">Custom</span>
        </button>
      </div>
      {value === "custom" && (
        <div className="flex items-center gap-2 mt-1.5">
          <input
            type="color"
            value={customValue ?? "#000000"}
            onChange={(e) => onChange("custom", e.target.value)}
            className="size-8 rounded cursor-pointer border border-border/60 bg-transparent p-0.5"
          />
          <input
            type="text"
            value={customValue ?? ""}
            onChange={(e) => onChange("custom", e.target.value)}
            placeholder="#000000"
            className="flex-1 border border-border/60 bg-background/80 px-2.5 py-1.5 text-xs outline-none focus:border-primary transition-colors rounded-sm placeholder:text-muted-foreground/40 font-mono"
          />
        </div>
      )}
    </div>
  );
}
