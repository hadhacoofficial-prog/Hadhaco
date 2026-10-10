import { describe, expect, it } from "vitest";
import { GA_MEASUREMENT_ID, gaHeadScripts } from "../analytics";
import { buildCsp } from "../csp";

describe("gaHeadScripts", () => {
  it("emits nothing when disabled (dev/test)", () => {
    expect(gaHeadScripts(false)).toEqual([]);
  });

  it("emits the async loader then the config snippet when enabled", () => {
    const scripts = gaHeadScripts(true);
    expect(scripts).toHaveLength(2);
    expect(scripts[0]).toEqual({
      src: `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`,
      async: true,
    });
    expect(scripts[1].children).toContain("window.dataLayer=window.dataLayer||[]");
    expect(scripts[1].children).toContain(`gtag('config','${GA_MEASUREMENT_ID}')`);
  });

  it("uses the Hadha GA4 measurement id", () => {
    expect(GA_MEASUREMENT_ID).toBe("G-MB0541PXVD");
  });
});

describe("CSP allows Google tag", () => {
  const csp = buildCsp("abc");
  const directive = (name: string) =>
    csp
      .split("; ")
      .find((d) => d.startsWith(`${name} `))
      ?.split(" ") ?? [];

  it("script-src allows googletagmanager.com", () => {
    expect(directive("script-src")).toContain("https://www.googletagmanager.com");
  });

  it("connect-src allows GA collection endpoints", () => {
    const connect = directive("connect-src");
    expect(connect).toContain("https://www.google-analytics.com");
    expect(connect).toContain("https://*.google-analytics.com");
    expect(connect).toContain("https://*.analytics.google.com");
  });
});
