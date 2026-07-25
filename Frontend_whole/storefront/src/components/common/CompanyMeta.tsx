import { useEffect } from "react";
import { usePublicCompanyConfig } from "@/hooks/company/useCompanyConfig";

/**
 * Dynamically updates document <title>, meta description, author,
 * og:site_name, and theme-color based on Company Settings from the API.
 *
 * Renders inside the router context (after providers) so the static
 * defaults in __root.tsx head() are replaced once config loads.
 */
export function CompanyMeta() {
  const { data: config } = usePublicCompanyConfig();

  useEffect(() => {
    if (!config) return;

    const name = config.brand_name || config.name || "Hadha Silver Jewellery";
    const tagline = config.tagline || "92.5 Silver Jewellery";
    const title = config.default_meta_title || `${name} | ${tagline}`;
    const description =
      config.default_meta_description ||
      config.description ||
      "Premium 92.5 Silver Jewellery — handcrafted, traditional, timeless.";
    const themeColor = config.theme_color || "#A8C8E8";

    document.title = title;

    const setMeta = (nameAttr: string, content: string, property?: string) => {
      let el: HTMLMetaElement | null = null;
      if (property) {
        el = document.querySelector(`meta[property="${property}"]`) as HTMLMetaElement | null;
      } else {
        el = document.querySelector(`meta[name="${nameAttr}"]`) as HTMLMetaElement | null;
      }
      if (el) {
        el.setAttribute("content", content);
      } else {
        el = document.createElement("meta");
        if (property) {
          el.setAttribute("property", property);
        } else {
          el.setAttribute("name", nameAttr);
        }
        el.setAttribute("content", content);
        document.head.appendChild(el);
      }
    };

    setMeta("description", description);
    setMeta("author", name);
    setMeta("theme-color", themeColor);
    setMeta("og:site_name", name, "og:site_name");
    setMeta("og:title", title, "og:title");
    setMeta("og:description", description, "og:description");
  }, [config]);

  return null;
}
