/**
 * 上传并裁切 (M5.5): the box of the output spec's aspect the user places on a picture of their
 * own, in the picture's pixels. The backend cuts the largest box of the aspect inside it and
 * scales it to the delivery size (`media/image.py:frame_rect`); these only place the box.
 */
import type { CropBox } from "@/api/hooks/pictures";

/** The smallest box is this share of the largest one (滚轮缩放). */
export const MIN_SCALE = 0.25;

/** Where the box sits along the picture's free side (居中 / 靠左 / 靠右, or top / bottom). */
export type CropAnchor = "start" | "center" | "end";

/** The largest box of ratio `rw:rh` inside a `w × h` picture. */
export function largestBox(w: number, h: number, rw: number, rh: number): { w: number; h: number } {
  return w * rh > h * rw ? { w: (h * rw) / rh, h } : { w, h: (w * rh) / rw };
}

/** The picture is wider than the frame: the box moves left and right (else up and down). */
export function slidesSideways(w: number, h: number, rw: number, rh: number): boolean {
  return w * rh > h * rw;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** The box at `scale` of the largest one, centred on (`cx`, `cy`), kept inside the picture. */
export function boxAt(
  w: number,
  h: number,
  rw: number,
  rh: number,
  scale: number,
  cx: number,
  cy: number,
): CropBox {
  const big = largestBox(w, h, rw, rh);
  const s = clamp(scale, MIN_SCALE, 1);
  const bw = big.w * s;
  const bh = big.h * s;
  return {
    x: clamp(cx - bw / 2, 0, w - bw),
    y: clamp(cy - bh / 2, 0, h - bh),
    w: bw,
    h: bh,
  };
}

/** The largest box, at the start, centre or end of the picture's free side. */
export function anchoredBox(
  w: number,
  h: number,
  rw: number,
  rh: number,
  anchor: CropAnchor,
): CropBox {
  const big = largestBox(w, h, rw, rh);
  const at = (free: number) => (anchor === "start" ? 0 : anchor === "end" ? free : free / 2);
  return { x: at(w - big.w), y: at(h - big.h), w: big.w, h: big.h };
}

/** Whole pixels, still inside the picture (what the upload sends). */
export function roundBox(box: CropBox, w: number, h: number): CropBox {
  const bw = Math.max(1, Math.min(w, Math.round(box.w)));
  const bh = Math.max(1, Math.min(h, Math.round(box.h)));
  return {
    x: clamp(Math.round(box.x), 0, w - bw),
    y: clamp(Math.round(box.y), 0, h - bh),
    w: bw,
    h: bh,
  };
}

/** `9:16` → [9, 16]. */
export function ratioOf(aspect: string): [number, number] {
  const [a, b] = aspect.split(":").map(Number);
  return [a || 1, b || 1];
}
