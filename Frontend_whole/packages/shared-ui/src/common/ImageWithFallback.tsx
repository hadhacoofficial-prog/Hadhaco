import { useState, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { ImageOff } from "lucide-react";
import { cn } from "@hadha/shared-utils";
import { Skeleton } from "../ui/skeleton";

interface ImageWithFallbackProps
  extends Omit<ComponentPropsWithoutRef<"img">, "className" | "onLoad" | "onError"> {
  className?: string;
  imgClassName?: string;
  fallback?: ReactNode;
}

export function ImageWithFallback({
  src,
  alt,
  className,
  imgClassName,
  fallback,
  loading = "lazy",
  ...props
}: ImageWithFallbackProps) {
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");

  return (
    <div className={cn("relative overflow-hidden", className)}>
      {status === "loading" && <Skeleton className="absolute inset-0 rounded-none" />}
      {status === "error" ? (
        (fallback ?? (
          <div className="flex size-full items-center justify-center bg-secondary text-muted-foreground">
            <ImageOff className="size-6" />
          </div>
        ))
      ) : (
        <img
          src={src}
          alt={alt}
          loading={loading}
          decoding="async"
          onLoad={() => setStatus("loaded")}
          onError={() => setStatus("error")}
          className={cn(
            "size-full object-cover transition-opacity duration-300",
            status === "loaded" ? "opacity-100" : "opacity-0",
            imgClassName,
          )}
          {...props}
        />
      )}
    </div>
  );
}
