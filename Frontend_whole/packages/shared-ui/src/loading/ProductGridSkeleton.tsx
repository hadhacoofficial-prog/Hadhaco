import { cn } from "@hadha/shared-utils";
import { ProductCardSkeleton } from "./ProductCardSkeleton";

interface ProductGridSkeletonProps {
  count?: number;
  className?: string;
}

export function ProductGridSkeleton({ count = 12, className }: ProductGridSkeletonProps) {
  return (
    <div
      className={cn("grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-5 gap-y-10", className)}
    >
      {Array.from({ length: count }).map((_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </div>
  );
}
