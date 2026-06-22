import markAsset from "@/assets/hadha-mark.png";

export function PageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-background/85 backdrop-blur-sm">
      <div className="relative">
        <img
          src={markAsset}
          alt="Hadha"
          className="size-20 md:size-24 object-contain"
          style={{ animation: "hadha-pulse 1.4s ease-in-out infinite" }}
        />
      </div>
      <div className="mt-6 h-[2px] w-32 overflow-hidden rounded-full bg-secondary">
        <div className="h-full w-full silver-shimmer" />
      </div>
      <p className="mt-4 text-[10px] uppercase tracking-[0.3em] text-muted-foreground font-sans-ui">
        {label}
      </p>
    </div>
  );
}
