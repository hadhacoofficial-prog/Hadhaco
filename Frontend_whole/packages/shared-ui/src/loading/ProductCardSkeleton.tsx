import { Skeleton } from "../ui/skeleton";

export function ProductCardSkeleton() {
  return (
    <article className="relative">
      <div className="aspect-square overflow-hidden bg-muted animate-pulse" />
      <div className="pt-4 pb-2 px-1">
        <Skeleton className="h-3 w-20 mb-1.5" />
        <Skeleton className="h-4 w-3/4 mb-1" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-5 w-1/3 mt-2" />
      </div>
    </article>
  );
}
