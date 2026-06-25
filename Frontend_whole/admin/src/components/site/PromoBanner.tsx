import bannerAsset from "@/assets/banner.jpg";
import { ArrowRight } from "lucide-react";
import type { ImageBannerConfig } from "@/types/cms";

const DEFAULTS: ImageBannerConfig = {
  title: "The Bugadi Edit",
  subtitle: "Press-on temple silhouettes in solid 92.5 silver.",
  desktop_image_url: "",
  cta_text: "Shop the edit",
  cta_url: "/collections",
};

interface PromoBannerProps {
  config?: Partial<ImageBannerConfig>;
}

export function PromoBanner({ config }: PromoBannerProps) {
  const c = { ...DEFAULTS, ...config };
  const image = c.desktop_image_url || bannerAsset;

  return (
    <section className="relative h-[55vh] min-h-[400px] overflow-hidden">
      <img
        src={image}
        alt=""
        loading="lazy"
        width={1920}
        height={720}
        className="absolute inset-0 w-full h-full object-cover"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-primary/70 via-primary/30 to-transparent" />
      <div className="relative z-10 h-full flex flex-col items-center justify-end text-center px-6 pb-16 md:pb-20 text-primary-foreground">
        <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-4">Limited offer</p>
        {c.title && (
          <h2 className="font-display text-4xl md:text-6xl max-w-3xl leading-tight">{c.title}</h2>
        )}
        {c.subtitle && <p className="mt-4 max-w-xl text-primary-foreground/85">{c.subtitle}</p>}
        <a
          href={c.cta_url || "/collections"}
          className="group mt-7 inline-flex items-center gap-3 bg-background text-foreground px-7 py-3.5 text-xs tracking-[0.22em] uppercase hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          {c.cta_text || "Shop the edit"}
          <ArrowRight className="size-4 group-hover:translate-x-1 transition-transform" />
        </a>
      </div>
    </section>
  );
}
