import { describe, expect, it } from "vitest";
import { CropGeometryError, defaultCropBox, validateAndClampCropBox } from "./cropMath";

describe("validateAndClampCropBox", () => {
  it("returns the box unchanged when it fits", () => {
    const box = { x: 10, y: 10, width: 50, height: 50 };
    expect(validateAndClampCropBox(box, 100, 100, false)).toEqual(box);
  });

  it("throws when strictBounds is true and the box doesn't fit", () => {
    const box = { x: -10, y: 0, width: 50, height: 50 };
    expect(() => validateAndClampCropBox(box, 100, 100, true)).toThrow(CropGeometryError);
  });

  it("clamps negative origin when strictBounds is false", () => {
    const box = { x: -10, y: -10, width: 50, height: 50 };
    const result = validateAndClampCropBox(box, 100, 100, false);
    expect(result).toEqual({ x: 0, y: 0, width: 40, height: 40 });
  });

  it("clamps overflow past the right/bottom edge", () => {
    const box = { x: 80, y: 80, width: 50, height: 50 };
    const result = validateAndClampCropBox(box, 100, 100, false);
    expect(result.width).toBe(20);
    expect(result.height).toBe(20);
  });
});

describe("defaultCropBox", () => {
  it("returns the full image for a null aspect ratio", () => {
    const result = defaultCropBox(800, 600, null);
    expect(result).toEqual({ x: 0, y: 0, width: 800, height: 600 });
  });

  it("centers a square crop inside a wider-than-tall image", () => {
    const result = defaultCropBox(1000, 500, 1);
    expect(result.width).toBe(500);
    expect(result.height).toBe(500);
    expect(result.x).toBe(250);
    expect(result.y).toBe(0);
  });

  it("centers a wide crop inside a taller-than-wide image", () => {
    const result = defaultCropBox(500, 1000, 2);
    expect(result.width).toBe(500);
    expect(result.height).toBe(250);
    expect(result.x).toBe(0);
    expect(result.y).toBe(375);
  });
});
