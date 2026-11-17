import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { prepareReviewPhoto, REVIEW_PHOTO_MAX_EDGE, ReviewPhotoError } from "@/lib/reviewPhoto";

// jsdom has neither createImageBitmap nor a drawing canvas: stand both in,
// recording the size the photo is drawn at and the encode settings.
const drawn: { width: number; height: number; type?: string; quality?: number }[] = [];
const close = vi.fn();

class FakeOffscreenCanvas {
  constructor(
    public width: number,
    public height: number,
  ) {}
  getContext() {
    return { fillStyle: "", fillRect: vi.fn(), drawImage: vi.fn() };
  }
  async convertToBlob(opts: { type: string; quality: number }) {
    drawn.push({ width: this.width, height: this.height, ...opts });
    return new Blob(["jpeg"], { type: opts.type });
  }
}

function bitmapOf(width: number, height: number) {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(async () => ({ width, height, close })),
  );
}

const photo = (name = "IMG_1234.HEIC.png", type = "image/png") =>
  new File(["original-bytes"], name, { type, lastModified: 42 });

describe("prepareReviewPhoto", () => {
  beforeEach(() => {
    drawn.length = 0;
    close.mockClear();
    vi.stubGlobal("OffscreenCanvas", FakeOffscreenCanvas);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shrinks a large photo to the max edge as JPEG, keeping its aspect", async () => {
    bitmapOf(4032, 3024);
    const out = await prepareReviewPhoto(photo());

    expect(drawn).toEqual([
      { width: REVIEW_PHOTO_MAX_EDGE, height: 1200, type: "image/jpeg", quality: 0.85 },
    ]);
    expect(out.type).toBe("image/jpeg");
    expect(out.name).toBe("IMG_1234.HEIC.jpg");
    expect(out.lastModified).toBe(42);
    expect(close).toHaveBeenCalledOnce();
  });

  it("never upscales a small photo", async () => {
    bitmapOf(480, 300);
    await prepareReviewPhoto(photo());
    expect(drawn[0]).toMatchObject({ width: 480, height: 300 });
  });

  it("rejects a photo under the minimum size before upload", async () => {
    bitmapOf(480, 150);
    await expect(prepareReviewPhoto(photo())).rejects.toThrow(
      new ReviewPhotoError("This photo is too small. Please choose one at least 200x200 pixels."),
    );
    expect(drawn).toHaveLength(0);
    expect(close).toHaveBeenCalledOnce();
  });

  it("rejects a file the browser cannot decode", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => {
        throw new DOMException("bad", "InvalidStateError");
      }),
    );
    await expect(prepareReviewPhoto(photo())).rejects.toBeInstanceOf(ReviewPhotoError);
  });

  it("rejects a non-image file without decoding it", async () => {
    bitmapOf(800, 800);
    await expect(prepareReviewPhoto(photo("notes.pdf", "application/pdf"))).rejects.toThrow(
      /choose a photo/,
    );
    expect(createImageBitmap).not.toHaveBeenCalled();
  });
});
