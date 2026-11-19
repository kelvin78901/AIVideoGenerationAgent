import { Brush, Eraser, Trash2, Undo2 } from "lucide-react";
import { useRef, useState, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useInpaint } from "@/api/hooks/pictures";
import type { Where } from "@/api/schemas/common";
import type { PictureTarget } from "@/components/pictures/RedrawDialog";
import { useWhereChoices } from "@/components/pictures/useWhereChoices";
import { WherePicker } from "@/components/pictures/WherePicker";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/form";
import { ratioOf } from "@/lib/crop";
import { maskBlob } from "@/lib/mask";

/** The painting canvas's long edge; the backend scales the mask to the picture. */
const CANVAS_LONG = 1024;
/** How far past the painted edge a take's repair reaches, in the take's pixels: the workflow
 * grows the mask 16 px and feathers it 8 px (`workflows/vace-inpaint`). */
const TAKE_REACH_PX = 24;
const UNDO_STEPS = 20;
/** The stroke colour on screen (shown at half opacity). */
const PAINT = "rgb(230, 40, 40)";

/** 视频局部修复 of a take (M6 草图 G2): painted on its frames, one mask for the whole take, only
 * locally (Wan VACE). */
export interface TakeInpaint {
  /** The take's clip, to look at another frame; the poster (`target.src`) when null. */
  video: string | null;
  /** The route's model name. */
  model: string;
  /** About how long one take takes; null when unknown. */
  minutes: number | null;
  /** Where QA read the shot's on-screen text (`[x0, y0, x1, y1]` on 0–1): outlined, and a mask
   * reaching it is warned about (the writing would be redrawn, Kelvin 2026-11-18). */
  textRegions?: number[][];
}

/** 局部修复 (草图 S7): paint where the picture changes, say what goes there; one new candidate.
 * With `take`, a video take's region (草图 G2): the prompt is optional, the model fixed. */
export function InpaintDialog({
  target,
  take,
  onClose,
}: {
  target: PictureTarget | null;
  take?: TakeInpaint;
  onClose: () => void;
}) {
  return target ? (
    <InpaintForm
      key={target.versionId + target.idx}
      target={target}
      take={take}
      onClose={onClose}
    />
  ) : null;
}

function InpaintForm({
  target,
  take,
  onClose,
}: {
  target: PictureTarget;
  take: TakeInpaint | undefined;
  onClose: () => void;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const inpaint = useInpaint();
  const { choices, initial } = useWhereChoices("inpaint");
  const [at, setAt] = useState(0);
  const [length, setLength] = useState(0);
  const [onText, setOnText] = useState(false);
  const regions = take?.textRegions ?? [];
  const clip = useRef<HTMLVideoElement | null>(null);
  const [prompt, setPrompt] = useState("");
  const [where, setWhere] = useState<Where | null>(null);
  const [tool, setTool] = useState<"brush" | "eraser">("brush");
  const [size, setSize] = useState("32");
  const [painted, setPainted] = useState(false);
  const [steps, setSteps] = useState(0);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const undo = useRef<ImageData[]>([]);
  const last = useRef<{ x: number; y: number } | null>(null);
  const picked = where ?? initial;

  const [rw, rh] = target.w && target.h ? [target.w, target.h] : ratioOf(target.aspect);
  const cw = rw >= rh ? CANVAS_LONG : Math.round((CANVAS_LONG * rw) / rh);
  const ch = rw >= rh ? Math.round((CANVAS_LONG * rh) / rw) : CANVAS_LONG;

  const ctx = () => canvas.current?.getContext("2d") ?? null;
  const point = (e: PointerEvent<HTMLCanvasElement>) => {
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return { x: 0, y: 0, scale: 1 };
    const scale = el.width / r.width;
    return { x: (e.clientX - r.left) * scale, y: (e.clientY - r.top) * scale, scale };
  };
  const stroke = (e: PointerEvent<HTMLCanvasElement>) => {
    const c = ctx();
    const p = point(e);
    if (!c) return;
    const from = last.current ?? p;
    c.globalCompositeOperation = tool === "brush" ? "source-over" : "destination-out";
    c.strokeStyle = PAINT;
    c.lineCap = "round";
    c.lineJoin = "round";
    c.lineWidth = Math.max(1, Number(size) || 32) * p.scale;
    c.beginPath();
    c.moveTo(from.x, from.y);
    c.lineTo(p.x, p.y);
    c.stroke();
    last.current = p;
  };
  const down = (e: PointerEvent<HTMLCanvasElement>) => {
    const el = e.currentTarget;
    if ("setPointerCapture" in el && typeof el.setPointerCapture === "function")
      el.setPointerCapture(e.pointerId);
    const c = ctx();
    if (c) {
      undo.current = [...undo.current, c.getImageData(0, 0, cw, ch)].slice(-UNDO_STEPS);
      setSteps(undo.current.length);
    }
    last.current = null;
    stroke(e);
    if (tool === "brush") setPainted(true);
  };
  /** Whether the mask, as far as the repair reaches past it, covers any of the text. */
  const checkText = () => {
    const c = ctx();
    if (!c || !regions.length) return;
    const reach = Math.ceil((TAKE_REACH_PX * cw) / (target.w || cw));
    const hit = regions.some(([x0 = 0, y0 = 0, x1 = 0, y1 = 0]) => {
      const left = Math.max(0, Math.floor(x0 * cw) - reach);
      const top = Math.max(0, Math.floor(y0 * ch) - reach);
      const w = Math.min(cw, Math.ceil(x1 * cw) + reach) - left;
      const h = Math.min(ch, Math.ceil(y1 * ch) + reach) - top;
      if (w <= 0 || h <= 0) return false;
      const data = c.getImageData(left, top, w, h).data as Uint8ClampedArray | undefined;
      if (!data) return false;
      for (let i = 3; i < data.length; i += 4) if (data[i]) return true;
      return false;
    });
    setOnText(hit);
  };
  const clear = () => {
    ctx()?.clearRect(0, 0, cw, ch);
    undo.current = [];
    setSteps(0);
    setPainted(false);
    setOnText(false);
  };
  const back = () => {
    const prev = undo.current.at(-1);
    undo.current = undo.current.slice(0, -1);
    setSteps(undo.current.length);
    if (prev) ctx()?.putImageData(prev, 0, 0);
    if (!undo.current.length) setPainted(false);
    checkText();
  };

  const submit = async () => {
    if (!canvas.current) return;
    let mask: Blob;
    try {
      mask = await maskBlob(canvas.current);
    } catch {
      toast.error(t("pictures.inpaint.noCanvas"));
      return;
    }
    inpaint.mutate(
      {
        productId: target.productId,
        versionId: target.versionId,
        idx: target.idx,
        prompt,
        mask,
        where: !take && choices.length ? picked : undefined,
      },
      {
        onSuccess: () => {
          toast.info(
            take
              ? t("pictures.inpaint.take.started", { name: target.name })
              : t("pictures.inpaint.started", { name: target.name }),
          );
          onClose();
        },
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );
  };

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent className="max-w-3xl gap-3.5" closeLabel={t("pictures.cancel")}>
        <DialogTitle className="text-base font-bold">
          {take
            ? t("pictures.inpaint.take.title", { name: target.name })
            : t("pictures.inpaint.title", { name: target.name })}
        </DialogTitle>
        <DialogDescription className="sr-only">
          {take ? t("pictures.inpaint.take.keep") : t("pictures.inpaint.keep")}
        </DialogDescription>
        <div className="flex flex-col gap-4 sm:flex-row">
          <div className="flex w-full max-w-60 shrink-0 flex-col gap-1.5 self-start">
            <div
              className="relative w-full overflow-hidden rounded-md bg-media"
              style={{ aspectRatio: `${rw} / ${rh}` }}
            >
              {take?.video ? (
                <video
                  src={take.video}
                  poster={target.src ?? undefined}
                  muted
                  playsInline
                  preload="metadata"
                  aria-label={target.name}
                  ref={clip}
                  onLoadedMetadata={(e) => setLength(e.currentTarget.duration || 0)}
                  className="absolute inset-0 size-full object-cover select-none"
                />
              ) : target.src ? (
                <img
                  src={target.src}
                  alt={target.name}
                  draggable={false}
                  className="absolute inset-0 size-full object-cover select-none"
                />
              ) : null}
              <canvas
                ref={canvas}
                width={cw}
                height={ch}
                aria-label={t("pictures.inpaint.canvas")}
                className="absolute inset-0 size-full cursor-crosshair touch-none opacity-50"
                onPointerDown={down}
                onPointerMove={(e) => {
                  if (e.buttons & 1 || e.pressure > 0) stroke(e);
                }}
                onPointerUp={() => {
                  last.current = null;
                  checkText();
                }}
                onPointerLeave={() => (last.current = null)}
              />
              {regions.map(([x0 = 0, y0 = 0, x1 = 0, y1 = 0], i) => (
                <span
                  key={i}
                  aria-hidden
                  className="pointer-events-none absolute rounded-sm border border-dashed border-amber-300"
                  style={{
                    left: `${x0 * 100}%`,
                    top: `${y0 * 100}%`,
                    width: `${(x1 - x0) * 100}%`,
                    height: `${(y1 - y0) * 100}%`,
                  }}
                />
              ))}
              {take ? (
                <span className="absolute top-1.5 left-1.5 rounded bg-white px-1.5 py-0.5 text-[11px] text-neutral-900">
                  {at ? `${at.toFixed(1)}s` : t("pictures.inpaint.take.frame")}
                </span>
              ) : null}
            </div>
            {take?.video && length > 0 ? (
              <input
                type="range"
                min={0}
                max={length}
                step={0.1}
                value={at}
                aria-label={t("pictures.inpaint.take.scrub")}
                onChange={(e) => {
                  const time = Number(e.target.value);
                  setAt(time);
                  if (clip.current) clip.current.currentTime = time;
                }}
                className="w-full accent-primary"
              />
            ) : null}
            {take ? (
              <span className="text-xs text-muted-foreground">
                {t("pictures.inpaint.take.scrub")}
              </span>
            ) : null}
          </div>
          <div className="flex min-w-0 grow flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <SegmentedControl
                size="sm"
                label={t("pictures.inpaint.tool")}
                value={tool}
                onChange={setTool}
                options={[
                  {
                    value: "brush",
                    label: (
                      <>
                        <Brush aria-hidden className="size-3.5" />
                        {t("pictures.inpaint.brush")}
                      </>
                    ),
                  },
                  {
                    value: "eraser",
                    label: (
                      <>
                        <Eraser aria-hidden className="size-3.5" />
                        {t("pictures.inpaint.eraser")}
                      </>
                    ),
                  },
                ]}
              />
              <Label htmlFor="inpaint-size" className="text-xs text-muted-foreground">
                {t("pictures.inpaint.size")}
              </Label>
              <Input
                id="inpaint-size"
                type="number"
                min={4}
                max={200}
                className="h-8 w-16"
                value={size}
                onChange={(e) => setSize(e.target.value)}
              />
              <Button size="sm" variant="outline" disabled={!steps} onClick={back}>
                <Undo2 aria-hidden />
                {t("pictures.inpaint.undo")}
              </Button>
              <Button size="sm" variant="outline" disabled={!steps} onClick={clear}>
                <Trash2 aria-hidden />
                {t("pictures.inpaint.clear")}
              </Button>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="inpaint-prompt">
                {take ? t("pictures.inpaint.take.prompt") : t("pictures.inpaint.prompt")}
              </Label>
              <Textarea
                id="inpaint-prompt"
                rows={3}
                maxLength={2000}
                value={prompt}
                placeholder={
                  take ? t("pictures.inpaint.take.placeholder") : t("pictures.inpaint.placeholder")
                }
                onChange={(e) => setPrompt(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="text-sm font-medium">{t("pictures.model")}</div>
              {take ? (
                <p className="text-sm text-muted-foreground">
                  {take.minutes
                    ? t("pictures.inpaint.take.model", { model: take.model, minutes: take.minutes })
                    : t("pictures.inpaint.take.modelPlain", { model: take.model })}
                </p>
              ) : (
                <WherePicker choices={choices} value={picked} onChange={setWhere} />
              )}
              <p className="text-xs text-muted-foreground">
                {take ? t("pictures.inpaint.take.keep") : t("pictures.inpaint.keep")}
              </p>
              {onText ? (
                <p role="status" className="text-xs font-medium text-tone-warn-fg">
                  {t("pictures.inpaint.take.onText")}
                </p>
              ) : null}
            </div>
          </div>
        </div>
        <DialogFooter className="items-center">
          <span className="mr-auto text-xs text-muted-foreground">
            {!painted
              ? t("pictures.inpaint.paintFirst")
              : take
                ? t("pictures.inpaint.take.result")
                : t("pictures.oneCandidate")}
          </span>
          <Button variant="outline" onClick={onClose}>
            {t("pictures.cancel")}
          </Button>
          <Button disabled={!painted || inpaint.isPending} onClick={() => void submit()}>
            {take ? t("pictures.inpaint.take.submit") : t("pictures.inpaint.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
