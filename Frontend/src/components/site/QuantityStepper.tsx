import { Minus, Plus } from "lucide-react";

export function QuantityStepper({
  value,
  onChange,
  min = 1,
  max = 99,
}: {
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
}) {
  return (
    <div className="inline-flex items-center border border-border">
      <button
        aria-label="Decrease"
        onClick={() => onChange(Math.max(min, value - 1))}
        className="size-9 flex items-center justify-center hover:bg-secondary transition"
      >
        <Minus className="size-3.5" />
      </button>
      <span className="w-10 text-center text-sm tabular-nums">{value}</span>
      <button
        aria-label="Increase"
        onClick={() => onChange(Math.min(max, value + 1))}
        className="size-9 flex items-center justify-center hover:bg-secondary transition"
      >
        <Plus className="size-3.5" />
      </button>
    </div>
  );
}
