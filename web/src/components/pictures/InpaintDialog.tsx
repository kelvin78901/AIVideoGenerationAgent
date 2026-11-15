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
const UNDO_STEPS = 20;
/** The stroke colour on screen (shown at half opacity). */
const PAINT = "rgb(230, 40, 40)";

/** 局部修复 (草图 S7): paint where the picture changes, say what goes there; one new candidate. */
export function InpaintDialog({
  target,
  onClose,
}: {
  target: PictureTarget | null;
  onClose: () => void;
}) {
  return target ? (
    <InpaintForm key={target.versionId + target.idx} target={target} onClose={onClose} />
  ) : null;
}

function InpaintForm({ target, onClose }: { target: PictureTarget; onClose: () => void }) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const inpaint = useInpaint();
  const { choices, initial } = useWhereChoices("inpaint");
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
  const clear = () => {
    ctx()?.clearRect(0, 0, cw, ch);
    undo.current = [];
    setSteps(0);
    setPainted(false);
  };
  const back = () => {
    const prev = undo.current.at(-1);
    undo.current = undo.current.slice(0, -1);
    setSteps(undo.current.length);
    if (prev) ctx()?.putImageData(prev, 0, 0);
    if (!undo.current.length) setPainted(false);
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
        where: choices.length ? picked : undefined,
      },
      {
        onSuccess: () => {
          toast.info(t("pictures.inpaint.started", { name: target.name }));
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
          {t("pictures.inpaint.title", { name: target.name })}
        </DialogTitle>
        <DialogDescription className="sr-only">{t("pictures.inpaint.keep")}</DialogDescription>
        <div className="flex flex-col gap-4 sm:flex-row">
          <div
            className="relative w-full max-w-60 shrink-0 self-start overflow-hidden rounded-md bg-media"
            style={{ aspectRatio: `${rw} / ${rh}` }}
          >
            {target.src ? (
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
              onPointerUp={() => (last.current = null)}
              onPointerLeave={() => (last.current = null)}
            />
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
              <Label htmlFor="inpaint-prompt">{t("pictures.inpaint.prompt")}</Label>
              <Textarea
                id="inpaint-prompt"
                rows={3}
                maxLength={2000}
                value={prompt}
                placeholder={t("pictures.inpaint.placeholder")}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="text-sm font-medium">{t("pictures.model")}</div>
              <WherePicker choices={choices} value={picked} onChange={setWhere} />
              <p className="text-xs text-muted-foreground">{t("pictures.inpaint.keep")}</p>
            </div>
          </div>
        </div>
        <DialogFooter className="items-center">
          <span className="mr-auto text-xs text-muted-foreground">
            {painted ? t("pictures.oneCandidate") : t("pictures.inpaint.paintFirst")}
          </span>
          <Button variant="outline" onClick={onClose}>
            {t("pictures.cancel")}
          </Button>
          <Button disabled={!painted || inpaint.isPending} onClick={() => void submit()}>
            {t("pictures.inpaint.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
