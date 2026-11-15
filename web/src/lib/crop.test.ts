import { anchoredBox, boxAt, largestBox, ratioOf, roundBox, slidesSideways } from "@/lib/crop";

describe("crop", () => {
  it("the largest 9:16 box of a 4:3 picture is its full height", () => {
    expect(roundBox(anchoredBox(4032, 3024, 9, 16, "center"), 4032, 3024)).toEqual({
      x: 1166,
      y: 0,
      w: 1701,
      h: 3024,
    });
    expect(slidesSideways(4032, 3024, 9, 16)).toBe(true);
  });

  it("a tall picture to a wide frame slides up and down", () => {
    expect(largestBox(1080, 1920, 16, 9)).toEqual({ w: 1080, h: 607.5 });
    expect(slidesSideways(1080, 1920, 16, 9)).toBe(false);
    expect(anchoredBox(1080, 1920, 16, 9, "end")).toEqual({ x: 0, y: 1312.5, w: 1080, h: 607.5 });
  });

  it("zooming keeps the centre and the box inside the picture", () => {
    const half = boxAt(4032, 3024, 9, 16, 0.5, 2016, 1512);
    expect(half.w).toBeCloseTo(850.5);
    expect(half.x + half.w / 2).toBeCloseTo(2016);
    // Dragged past the corner: it stops at the edge.
    expect(boxAt(4032, 3024, 9, 16, 0.5, 0, 0)).toMatchObject({ x: 0, y: 0 });
    // Never smaller than a quarter, never larger than the picture allows.
    expect(boxAt(4032, 3024, 9, 16, 0.01, 2016, 1512).h).toBeCloseTo(756);
    expect(boxAt(4032, 3024, 9, 16, 3, 2016, 1512).h).toBe(3024);
  });

  it("reads an aspect", () => {
    expect(ratioOf("21:9")).toEqual([21, 9]);
  });
});
