import { Minus, Plus } from "lucide-react";

export function QuantityStepper({
  value,
  onChange,
  min = 1,
  max = 99,
  disabled = false,
}: {
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
}) {
  const atMin = disabled || value <= min;
  const atMax = disabled || value >= max;
  return (
    <div
      className={`inline-flex items-center border border-border ${disabled ? "opacity-50" : ""}`}
    >
      <button
        aria-label="Decrease"
        disabled={atMin}
        onClick={() => onChange(Math.max(min, value - 1))}
        className="size-9 flex items-center justify-center hover:bg-secondary transition disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Minus className="size-3.5" />
      </button>
      <span className="w-10 text-center text-sm tabular-nums">{value}</span>
      <button
        aria-label="Increase"
        disabled={atMax}
        onClick={() => onChange(Math.min(max, value + 1))}
        className="size-9 flex items-center justify-center hover:bg-secondary transition disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Plus className="size-3.5" />
      </button>
    </div>
  );
}
