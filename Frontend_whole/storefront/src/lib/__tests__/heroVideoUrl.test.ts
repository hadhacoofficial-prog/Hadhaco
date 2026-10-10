import { describe, expect, it } from "vitest";
import {
  hasVideoBackground,
  videoUrlProblem,
  type HeroSlideMedia,
} from "@hadha/shared-types";

describe("videoUrlProblem", () => {
  it.each([
    [undefined],
    [""],
    ["   "],
    ["https://cdn.hadha.co/cms/hero/intro.mp4"],
    ["https://cdn.hadha.co/cms/hero/intro.webm?v=2"],
    ["https://videos.pexels.com/video-files/3571264/3571264-uhd.mp4"],
    ["/media/intro.mp4"],
  ])("accepts %s", (url) => {
    expect(videoUrlProblem(url)).toBeNull();
  });

  it.each([
    ["https://www.instagram.com/popula_dabba_?xtok=abc&utm_source=qr"],
    ["https://www.youtube.com/watch?v=abc"],
    ["https://example.com/video.mp4"],
    ["http://cdn.hadha.co/intro.mp4"],
    ["https://cdn.hadha.co/page"],
    ["//cdn.hadha.co/intro.mp4"],
    ["https://cdn.hadha.co.evil.com/intro.mp4"],
  ])("rejects %s", (url) => {
    expect(videoUrlProblem(url)).toBeTruthy();
  });
});

describe("hasVideoBackground", () => {
  const base = { desktop_image_url: "https://cdn.hadha.co/a.jpg" };

  it("ignores an unplayable stored URL so the image is used", () => {
    const media: HeroSlideMedia = {
      ...base,
      video_url: "https://www.instagram.com/x",
    };
    expect(hasVideoBackground(media)).toBe(false);
  });

  it("keeps a valid video", () => {
    const media: HeroSlideMedia = {
      ...base,
      video_url: "https://cdn.hadha.co/v.mp4",
    };
    expect(hasVideoBackground(media)).toBe(true);
  });
});
