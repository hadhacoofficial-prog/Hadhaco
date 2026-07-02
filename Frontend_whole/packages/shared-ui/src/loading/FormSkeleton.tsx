import { cn } from "@hadha/shared-utils";
import { Skeleton } from "../ui/skeleton";

interface FormSkeletonProps {
  fields?: number;
  columns?: 1 | 2;
  showTitle?: boolean;
  className?: string;
}

export function FormSkeleton({
  fields = 6,
  columns = 1,
  showTitle = false,
  className,
}: FormSkeletonProps) {
  return (
    <div className={cn("space-y-4", className)}>
      {showTitle && (
        <div className="flex items-center gap-2 pb-2 border-b border-border">
          <Skeleton className="size-4" />
          <Skeleton className="h-4 w-32" />
        </div>
      )}
      <div className={cn("grid gap-4", columns === 2 && "grid-cols-2")}>
        {Array.from({ length: fields }).map((_, i) => (
          <div key={i} className="space-y-1.5">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-9 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
