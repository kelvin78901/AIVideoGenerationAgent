/** 局部修复 (M5.5): the painted strokes as the mask `POST /versions/{id}/inpaint` takes. */

/**
 * The mask the backend reads (`media/image.py:mask_for`): black, white where it was painted, the
 * canvas's shape (the picture's).
 */
export function maskBlob(strokes: HTMLCanvasElement): Promise<Blob> {
  const out = document.createElement("canvas");
  out.width = strokes.width;
  out.height = strokes.height;
  const ctx = out.getContext("2d");
  if (!ctx) return Promise.reject(new Error("no canvas"));
  ctx.drawImage(strokes, 0, 0);
  ctx.globalCompositeOperation = "source-in";
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, out.width, out.height);
  ctx.globalCompositeOperation = "destination-over";
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, out.width, out.height);
  return new Promise((resolve, reject) =>
    out.toBlob((b) => (b ? resolve(b) : reject(new Error("no mask"))), "image/png"),
  );
}
