import { X } from "lucide-react";

import { cn } from "@hadha/shared-utils";

export interface FilterChip {
  key: string;
  /** e.g. "Payment: Paid" — the group name keeps meaning without colour. */
  label: string;
  onRemove: () => void;
}

interface ActiveFilterChipsProps {
  chips: FilterChip[];
  onClearAll?: () => void;
  className?: string;
  /** Storefront uses roomier, uppercase chips; admin uses compact ones. */
  variant?: "admin" | "storefront";
}

/** Removable chips for every active filter, plus "Clear all". */
export function ActiveFilterChips({
  chips,
  onClearAll,
  className,
  variant = "admin",
}: ActiveFilterChipsProps) {
  if (chips.length === 0) return null;
  const storefront = variant === "storefront";
  return (
    <div
      role="region"
      aria-label="Active filters"
      className={cn("flex flex-wrap items-center gap-2", className)}
    >
      {chips.map((c) => (
        <button
          key={c.key}
          type="button"
          onClick={c.onRemove}
          aria-label={`Remove filter ${c.label}`}
          className={cn(
            "inline-flex items-center gap-1.5 border border-border bg-card hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            storefront
              ? "min-h-9 px-3 py-1.5 text-xs uppercase tracking-[0.14em]"
              : "px-2.5 py-1 text-xs",
          )}
        >
          <span>{c.label}</span>
          <X aria-hidden className="size-3" />
        </button>
      ))}
      {onClearAll && chips.length > 0 && (
        <button
          type="button"
          onClick={onClearAll}
          className={cn(
            "text-xs underline underline-offset-4 text-muted-foreground hover:text-foreground min-h-9 px-1",
            storefront && "uppercase tracking-[0.14em]",
          )}
        >
          Clear all
        </button>
      )}
    </div>
  );
}
