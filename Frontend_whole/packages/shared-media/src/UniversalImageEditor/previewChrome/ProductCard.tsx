import type { PreviewChromeProps } from "./types";

/** Miniature replica of the storefront's square product grid tile. */
export function ProductCardChrome({ imageSrc }: PreviewChromeProps) {
  return (
    <div className="w-full max-w-40 rounded-md border bg-card overflow-hidden">
      <div className="aspect-square bg-secondary">
        {imageSrc && (
          <img src={imageSrc} alt="" className="w-full h-full object-cover" draggable={false} />
        )}
      </div>
      <div className="p-2 space-y-1">
        <div className="h-2 w-3/4 rounded bg-muted" />
        <div className="h-2 w-1/2 rounded bg-muted" />
      </div>
    </div>
  );
}
