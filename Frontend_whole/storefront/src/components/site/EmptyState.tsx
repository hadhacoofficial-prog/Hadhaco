import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="border border-border bg-card py-20 px-6 text-center">
      {icon && (
        <div className="mx-auto mb-5 size-14 flex items-center justify-center rounded-full bg-secondary text-foreground/70">
          {icon}
        </div>
      )}
      <h2 className="font-display text-2xl mb-2">{title}</h2>
      {description && (
        <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">{description}</p>
      )}
      {action}
    </div>
  );
}
