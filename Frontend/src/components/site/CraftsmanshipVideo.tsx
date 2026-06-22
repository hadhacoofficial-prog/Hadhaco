import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import type { VideoSectionConfig } from "@/types/cms";

const DEFAULT_VIDEO_URL =
  "https://videos.pexels.com/video-files/11353206/11353206-hd_1920_1080_25fps.mp4";

interface CraftsmanshipVideoProps {
  config?: Partial<VideoSectionConfig>;
}

export function CraftsmanshipVideo({ config }: CraftsmanshipVideoProps) {
  const videoUrl = config?.mp4_url || DEFAULT_VIDEO_URL;
  const posterUrl = config?.poster_url || undefined;
  const autoplay = config?.autoplay ?? true;
  const loop = config?.loop ?? true;
  const muted = config?.muted ?? true;
  const controls = config?.controls ?? false;

  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    setLoaded(false);
  }, [videoUrl]);

  return (
    <motion.section
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ duration: 1, ease: [0.2, 0.7, 0.2, 1] }}
      className="relative w-full overflow-hidden bg-foreground h-[400px] sm:h-[500px] md:h-[650px] lg:h-[750px] xl:h-[800px]"
      aria-label="Hadha craftsmanship film"
    >
      {!loaded && <div className="absolute inset-0 silver-shimmer opacity-40" aria-hidden="true" />}

      {videoUrl && (
        <video
          key={videoUrl}
          src={videoUrl}
          poster={posterUrl}
          autoPlay={autoplay}
          muted={muted}
          loop={loop}
          controls={controls}
          playsInline
          preload="auto"
          onLoadedData={() => setLoaded(true)}
          onCanPlay={() => setLoaded(true)}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-1000 ${
            loaded ? "opacity-100" : "opacity-0"
          }`}
        />
      )}
    </motion.section>
  );
}
