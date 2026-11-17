/**
 * Shrinks a customer's review photo in the browser before upload.
 *
 * Phone originals are 3-8 MB; sent as-is, three of them took longer than the
 * upload timeout on mobile data. Re-encoding to at most REVIEW_PHOTO_MAX_EDGE
 * px brings each to a few hundred KB, bakes in EXIF rotation, and decodes the
 * whole file up front, so an unreadable or too-small photo is rejected the
 * moment it is picked instead of after a slow upload.
 */

export const REVIEW_PHOTO_MAX_EDGE = 1600;
/** Must match the backend `review_photo` preset's min_resolution. */
export const REVIEW_PHOTO_MIN_SIDE = 200;
const JPEG_QUALITY = 0.85;

/** A rejection whose message can be shown to the shopper as-is. */
export class ReviewPhotoError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReviewPhotoError";
  }
}

const UNREADABLE = "We couldn't read this photo. Please choose a JPG, PNG or WebP image.";

type Canvas2D = {
  getContext(id: "2d"): CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D | null;
};

function makeCanvas(width: number, height: number): Canvas2D & { toJpeg(): Promise<Blob> } {
  if (typeof OffscreenCanvas !== "undefined") {
    const canvas = new OffscreenCanvas(width, height);
    return Object.assign(canvas, {
      toJpeg: () => canvas.convertToBlob({ type: "image/jpeg", quality: JPEG_QUALITY }),
    });
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return Object.assign(canvas, {
    toJpeg: () =>
      new Promise<Blob>((resolve, reject) =>
        canvas.toBlob(
          (blob) => (blob ? resolve(blob) : reject(new ReviewPhotoError(UNREADABLE))),
          "image/jpeg",
          JPEG_QUALITY,
        ),
      ),
  });
}

export async function prepareReviewPhoto(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) {
    throw new ReviewPhotoError("Please choose a photo (JPG, PNG or WebP).");
  }

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new ReviewPhotoError(UNREADABLE);
  }

  try {
    const { width, height } = bitmap;
    if (width < REVIEW_PHOTO_MIN_SIDE || height < REVIEW_PHOTO_MIN_SIDE) {
      throw new ReviewPhotoError(
        `This photo is too small. Please choose one at least ${REVIEW_PHOTO_MIN_SIDE}x${REVIEW_PHOTO_MIN_SIDE} pixels.`,
      );
    }
    const scale = Math.min(1, REVIEW_PHOTO_MAX_EDGE / Math.max(width, height));
    const w = Math.round(width * scale);
    const h = Math.round(height * scale);

    const canvas = makeCanvas(w, h);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new ReviewPhotoError(UNREADABLE);
    // JPEG has no alpha: give transparent PNG/WebP areas a white backdrop.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(bitmap, 0, 0, w, h);
    const blob = await canvas.toJpeg();

    const base = file.name.replace(/\.[^.]*$/, "") || "photo";
    return new File([blob], `${base}.jpg`, { type: "image/jpeg", lastModified: file.lastModified });
  } finally {
    bitmap.close();
  }
}
