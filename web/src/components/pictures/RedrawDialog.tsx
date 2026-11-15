import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useRedraw } from "@/api/hooks/pictures";
import type { Where } from "@/api/schemas/common";
import type { Aspect } from "@/api/schemas/spec";
import { MediaThumb } from "@/components/MediaThumb";
import { useWhereChoices } from "@/components/pictures/useWhereChoices";
import { WherePicker } from "@/components/pictures/WherePicker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label, Textarea } from "@/components/ui/form";
import { Slider } from "@/components/ui/slider";

/** The picture being changed: product, version, picture number, how it looks. */
export interface PictureTarget {
  productId: string;
  versionId: string;
  idx: number;
  /** 「1-08 v2 · A」 */
  name: string;
  src: string | null;
  aspect: Aspect;
  seed: string;
  /** The picture's own size when known (a reference picture keeps its shape). */
  w?: number | null;
  h?: number | null;
}

/** The backend's default 改动幅度 (`redraw.DEFAULT_STRENGTH`). */
const DEFAULT_STRENGTH = 0.5;

/** 以这张为底重画 (草图 S6): what to change and how much; one new candidate. */
export function RedrawDialog({
  target,
  onClose,
}: {
  target: PictureTarget | null;
  onClose: () => void;
}) {
  return target ? (
    <RedrawForm key={target.versionId + target.idx} target={target} onClose={onClose} />
  ) : null;
}

function RedrawForm({ target, onClose }: { target: PictureTarget; onClose: () => void }) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const redraw = useRedraw();
  const { choices, initial } = useWhereChoices("redraw");
  const [prompt, setPrompt] = useState("");
  const [strength, setStrength] = useState(DEFAULT_STRENGTH);
  const [where, setWhere] = useState<Where | null>(null);
  const picked = where ?? initial;
  const submit = () =>
    redraw.mutate(
      {
        productId: target.productId,
        versionId: target.versionId,
        idx: target.idx,
        prompt,
        strength,
        where: choices.length ? picked : undefined,
      },
      {
        onSuccess: () => {
          toast.info(t("pictures.redraw.started", { name: target.name }));
          onClose();
        },
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );
  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent className="max-w-2xl gap-3.5" closeLabel={t("pictures.cancel")}>
        <DialogTitle className="text-base font-bold">
          {t("pictures.redraw.title", { name: target.name })}
        </DialogTitle>
        <DialogDescription className="sr-only">{t("pictures.redraw.foot")}</DialogDescription>
        <div className="flex flex-col gap-4 sm:flex-row">
          <div className="w-40 shrink-0">
            <MediaThumb
              aspect={target.aspect}
              seed={target.seed}
              src={target.src}
              alt={target.name}
            />
          </div>
          <div className="flex min-w-0 grow flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="redraw-prompt">{t("pictures.redraw.prompt")}</Label>
              <Textarea
                id="redraw-prompt"
                rows={3}
                maxLength={2000}
                value={prompt}
                placeholder={t("pictures.redraw.placeholder")}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="text-sm font-medium">{t("pictures.redraw.strength")}</div>
              <Slider
                min={0.1}
                max={1}
                step={0.05}
                value={[strength]}
                thumbLabel={t("pictures.redraw.strength")}
                onValueChange={(v) => setStrength(v[0] ?? DEFAULT_STRENGTH)}
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{t("pictures.redraw.small")}</span>
                <span>{t("pictures.redraw.medium")}</span>
                <span>{t("pictures.redraw.large")}</span>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="text-sm font-medium">{t("pictures.model")}</div>
              <WherePicker choices={choices} value={picked} onChange={setWhere} />
              {picked === "api" ? (
                <p className="text-xs text-muted-foreground">{t("pictures.redraw.apiNote")}</p>
              ) : null}
            </div>
          </div>
        </div>
        <DialogFooter className="items-center">
          <span className="mr-auto text-xs text-muted-foreground">{t("pictures.redraw.foot")}</span>
          <Button variant="outline" onClick={onClose}>
            {t("pictures.cancel")}
          </Button>
          <Button disabled={redraw.isPending} onClick={submit}>
            {t("pictures.redraw.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
