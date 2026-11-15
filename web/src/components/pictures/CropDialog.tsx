import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";

import type { CropBox } from "@/api/hooks/pictures";
import type { Aspect } from "@/api/schemas/spec";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  anchoredBox,
  boxAt,
  largestBox,
  ratioOf,
  roundBox,
  slidesSideways,
  type CropAnchor,
} from "@/lib/crop";

interface Dims {
  w: number;
  h: number;
}

/** The preview's largest size on screen. */
const VIEW_W = 420;
const VIEW_H = 315;
/** A keyboard nudge, as a share of the picture. */
const NUDGE = 0.02;

/**
 * 上传并裁切 (草图 S5): a box of the output spec's aspect on the user's picture — dragged,
 * scrolled to zoom, or put at the start / centre / end — sent in the picture's pixels; the
 * backend scales the cut-out to the delivery size. Smaller than the draft size: only a warning.
 */
export function CropDialog({
  file,
  title,
  aspect,
  draft,
  delivery,
  pending,
  onSubmit,
  onClose,
}: {
  file: File | null;
  title: string;
  aspect: Aspect;
  draft: Dims;
  delivery: Dims;
  pending: boolean;
  onSubmit: (box: CropBox) => void;
  onClose: () => void;
}) {
  return file ? (
    <CropForm
      key={`${file.name}-${file.size}-${file.lastModified}`}
      file={file}
      title={title}
      aspect={aspect}
      draft={draft}
      delivery={delivery}
      pending={pending}
      onSubmit={onSubmit}
      onClose={onClose}
    />
  ) : null;
}

function CropForm({
  file,
  title,
  aspect,
  draft,
  delivery,
  pending,
  onSubmit,
  onClose,
}: {
  file: File;
  title: string;
  aspect: Aspect;
  draft: Dims;
  delivery: Dims;
  pending: boolean;
  onSubmit: (box: CropBox) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation("components");
  // Let go once the picture is decoded (it stays on screen).
  const [url] = useState(() => URL.createObjectURL(file));
  const [rw, rh] = ratioOf(aspect);
  const [size, setSize] = useState<Dims | null>(null);
  const [box, setBox] = useState<CropBox | null>(null);
  const [anchor, setAnchor] = useState<CropAnchor | null>("center");
  const [broken, setBroken] = useState(false);
  const drag = useRef<{ x: number; y: number; box: CropBox; scale: number } | null>(null);

  const loaded = (w: number, h: number) => {
    if (!w || !h) return setBroken(true);
    setSize({ w, h });
    setBox(anchoredBox(w, h, rw, rh, "center"));
  };
  const view = size
    ? size.w / size.h > VIEW_W / VIEW_H
      ? { w: VIEW_W, h: (VIEW_W * size.h) / size.w }
      : { w: (VIEW_H * size.w) / size.h, h: VIEW_H }
    : { w: VIEW_W, h: VIEW_H };
  const scaleOf = (b: CropBox) => (size ? b.w / largestBox(size.w, size.h, rw, rh).w : 1);
  const move = (b: CropBox, dx: number, dy: number, scale = scaleOf(b)) =>
    size ? boxAt(size.w, size.h, rw, rh, scale, b.x + b.w / 2 + dx, b.y + b.h / 2 + dy) : b;

  const down = (e: PointerEvent<HTMLDivElement>) => {
    if (!box || !size) return;
    const el = e.currentTarget;
    if ("setPointerCapture" in el && typeof el.setPointerCapture === "function")
      el.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, box, scale: size.w / view.w };
  };
  const dragMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    setAnchor(null);
    setBox(move(d.box, (e.clientX - d.x) * d.scale, (e.clientY - d.y) * d.scale));
  };
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!box || !size) return;
    const step = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[
      e.key
    ];
    const zoom = e.key === "+" || e.key === "=" ? 0.95 : e.key === "-" ? 1.05 : null;
    if (!step && !zoom) return;
    e.preventDefault();
    setAnchor(null);
    setBox(
      step
        ? move(box, (step[0] ?? 0) * size.w * NUDGE, (step[1] ?? 0) * size.h * NUDGE)
        : move(box, 0, 0, scaleOf(box) * (zoom ?? 1)),
    );
  };

  const cut = box && size ? roundBox(box, size.w, size.h) : null;
  const low = cut ? cut.w < draft.w || cut.h < draft.h : false;
  const sideways = size ? slidesSideways(size.w, size.h, rw, rh) : true;
  const pct = (v: number, of: number) => `${(100 * v) / of}%`;

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent className="max-w-3xl gap-3.5" closeLabel={t("pictures.cancel")}>
        <DialogTitle className="text-base font-bold">{title}</DialogTitle>
        <DialogDescription className="sr-only">{t("pictures.crop.foot")}</DialogDescription>
        <div className="flex flex-col gap-4 sm:flex-row">
          <div
            className="relative shrink-0 self-start overflow-hidden rounded-md bg-media"
            style={{ width: view.w, maxWidth: "100%", aspectRatio: `${view.w} / ${view.h}` }}
            // Anywhere over the picture: up zooms in, down out.
            onWheel={(e) => {
              if (!box) return;
              setAnchor(null);
              setBox(move(box, 0, 0, scaleOf(box) * (e.deltaY > 0 ? 1.05 : 0.95)));
            }}
          >
            {!broken ? (
              <img
                src={url}
                alt={file.name}
                draggable={false}
                className="absolute inset-0 size-full object-contain select-none"
                onLoad={(e) => {
                  loaded(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight);
                  URL.revokeObjectURL(url);
                }}
                onError={() => {
                  setBroken(true);
                  URL.revokeObjectURL(url);
                }}
              />
            ) : null}
            {box && size ? (
              <div
                role="slider"
                tabIndex={0}
                aria-label={t("pictures.crop.box")}
                aria-valuetext={t("pictures.crop.boxValue", {
                  x: Math.round(box.x),
                  y: Math.round(box.y),
                  w: Math.round(box.w),
                  h: Math.round(box.h),
                })}
                className="absolute cursor-move touch-none border-2 border-white shadow-[0_0_0_999px_rgba(0,0,0,0.5)] outline-none focus-visible:ring-2 focus-visible:ring-ring"
                style={{
                  left: pct(box.x, size.w),
                  top: pct(box.y, size.h),
                  width: pct(box.w, size.w),
                  height: pct(box.h, size.h),
                }}
                onPointerDown={down}
                onPointerMove={dragMove}
                onPointerUp={() => (drag.current = null)}
                onKeyDown={key}
              />
            ) : null}
          </div>
          <div className="flex min-w-0 grow flex-col gap-2 text-sm">
            <div className="truncate font-medium">{file.name}</div>
            {broken ? (
              <p role="alert" className="text-destructive">
                {t("pictures.crop.broken")}
              </p>
            ) : size && cut ? (
              <p className="text-xs text-muted-foreground">
                {t("pictures.crop.source", { w: size.w, h: size.h })}
                <br />
                {t("pictures.crop.output", {
                  aspect,
                  cw: cut.w,
                  ch: cut.h,
                  w: delivery.w,
                  h: delivery.h,
                })}
              </p>
            ) : null}
            <div className="mt-1 text-sm font-medium">{t("pictures.crop.frame")}</div>
            <p className="text-xs text-muted-foreground">
              {t("pictures.crop.frameHint", { aspect })}
            </p>
            <SegmentedControl
              size="sm"
              label={t("pictures.crop.frame")}
              value={anchor ?? ("" as CropAnchor)}
              onChange={(a) => {
                setAnchor(a);
                if (size) setBox(anchoredBox(size.w, size.h, rw, rh, a));
              }}
              options={(["center", "start", "end"] as const).map((a) => ({
                value: a,
                label: t(`pictures.crop.anchor.${sideways ? "x" : "y"}.${a}`),
                disabled: !size,
              }))}
            />
            {low && cut ? (
              <p
                role="status"
                className="rounded-md border border-tone-warn-border bg-tone-warn-bg p-2 text-xs text-tone-warn-fg"
              >
                {t("pictures.crop.lowRes", { cw: cut.w, ch: cut.h, w: draft.w, h: draft.h })}
              </p>
            ) : null}
          </div>
        </div>
        <DialogFooter className="items-center">
          <span className="mr-auto text-xs text-muted-foreground">{t("pictures.crop.foot")}</span>
          <Button variant="outline" onClick={onClose}>
            {t("pictures.cancel")}
          </Button>
          <Button disabled={!cut || pending} onClick={() => cut && onSubmit(cut)}>
            {t("pictures.crop.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
