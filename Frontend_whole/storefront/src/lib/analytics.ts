/**
 * Google tag (GA4) for the storefront.
 *
 * Rendered through the router's head() so TanStack stamps the per-request CSP
 * nonce onto the inline snippet. Only emitted in production builds so local
 * dev and test runs never send hits.
 */

export const GA_MEASUREMENT_ID = "G-MB0541PXVD";

export interface HeadScript {
  src?: string;
  async?: boolean;
  children?: string;
}

export function gaHeadScripts(enabled: boolean = import.meta.env.PROD): HeadScript[] {
  if (!enabled) return [];
  return [
    {
      src: `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`,
      async: true,
    },
    {
      children:
        "window.dataLayer=window.dataLayer||[];" +
        "function gtag(){dataLayer.push(arguments);}" +
        "gtag('js',new Date());" +
        `gtag('config','${GA_MEASUREMENT_ID}');`,
    },
  ];
}
