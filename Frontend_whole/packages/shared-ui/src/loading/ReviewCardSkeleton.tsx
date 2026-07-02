import { Skeleton } from "../ui/skeleton";

export function ReviewCardSkeleton() {
  return (
    <article className="bg-background border border-border p-5 flex flex-col gap-4">
      <div className="flex flex-col md:flex-row md:items-start gap-4">
        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-16" />
          </div>
          <div className="flex items-center gap-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="size-3.5 rounded-full" />
            ))}
          </div>
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-3/4" />
        </div>
        <div className="flex gap-2 shrink-0 flex-wrap">
          <Skeleton className="h-8 w-20" />
          <Skeleton className="h-8 w-20" />
          <Skeleton className="h-8 w-20" />
        </div>
      </div>
    </article>
  );
}

export function ReviewListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <ReviewCardSkeleton key={i} />
      ))}
    </div>
  );
}
