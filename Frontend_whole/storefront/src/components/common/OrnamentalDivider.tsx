/**
 * Subtle South Indian temple-inspired ornamental divider.
 * Use sparingly between major sections.
 */
export function OrnamentalDivider({
  className = "",
  tone = "muted",
}: {
  className?: string;
  tone?: "muted" | "light";
}) {
  const stroke = tone === "light" ? "currentColor" : "var(--color-accent)";
  return (
    <div
      className={`flex items-center justify-center gap-4 text-muted-foreground/70 ${className}`}
      aria-hidden="true"
    >
      <span className="h-px flex-1 max-w-[120px] bg-gradient-to-r from-transparent to-current opacity-40" />
      <svg width="56" height="14" viewBox="0 0 56 14" fill="none" stroke={stroke} strokeWidth="1">
        <circle cx="28" cy="7" r="3" />
        <circle cx="28" cy="7" r="6" opacity="0.4" />
        <path d="M2 7 Q8 2 14 7 Q8 12 2 7 Z" />
        <path d="M54 7 Q48 2 42 7 Q48 12 54 7 Z" />
        <circle cx="18" cy="7" r="1" fill={stroke} />
        <circle cx="38" cy="7" r="1" fill={stroke} />
      </svg>
      <span className="h-px flex-1 max-w-[120px] bg-gradient-to-l from-transparent to-current opacity-40" />
    </div>
  );
}
