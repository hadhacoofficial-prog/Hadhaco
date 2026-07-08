import { ImageWithFallback } from "@hadha/shared-ui/common/ImageWithFallback";
import type { ImageBundle } from "@hadha/shared-types";

interface ResponsiveImageProps {
  bundle: ImageBundle;
  className?: string;
  imgClassName?: string;
  /** `sizes` attribute — required whenever the rendered width varies by
   * breakpoint (e.g. "(min-width: 1024px) 33vw, 100vw"); omit for
   * fixed-size renders (avatars, logos) where the browser doesn't need it. */
  sizes?: string;
  loading?: "lazy" | "eager";
  fetchPriority?: "high" | "low" | "auto";
}

/**
 * The only sanctioned way to render a URIS-managed image (architecture doc
 * §11) — builds `srcSet`/`sizes` from an ImageBundle and delegates
 * loading-state/error-fallback chrome to the existing `ImageWithFallback`.
 * Raw `<img src={someUrisUrl}>` should never appear for these images; see
 * the `no-raw-img-for-uris-assets` ESLint rule (eslintRules/noRawImg.ts) for
 * the (not-yet-enforced) repo-wide guardrail.
 */
export function ResponsiveImage({
  bundle,
  className,
  imgClassName,
  sizes,
  loading = "lazy",
  fetchPriority = "auto",
}: ResponsiveImageProps) {
  const srcSet = bundle.variants
    .slice()
    .sort((a, b) => a.width * a.dpr - b.width * b.dpr)
    .map((v) => `${v.url} ${v.width * v.dpr}w`)
    .join(", ");

  const fallback = bundle.variants[0]?.url;

  return (
    <ImageWithFallback
      src={fallback}
      srcSet={srcSet || undefined}
      sizes={srcSet ? sizes : undefined}
      alt={bundle.altText ?? ""}
      className={className}
      imgClassName={imgClassName}
      loading={loading}
      fetchPriority={fetchPriority}
      style={{ objectPosition: `${bundle.focusPoint.x * 100}% ${bundle.focusPoint.y * 100}%` }}
    />
  );
}
