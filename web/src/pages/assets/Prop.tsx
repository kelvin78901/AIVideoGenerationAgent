import { RefreshCw } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { useProducts, useRunProduct } from "@/api/hooks/products";
import type { Asset, AssetPatch, Physical } from "@/api/schemas/assets";
import type { Aspect } from "@/api/schemas/spec";
import { MediaLightbox } from "@/components/MediaLightbox";
import { MediaThumb } from "@/components/MediaThumb";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/form";
import { CARD_WIDTH } from "@/lib/cards";

const FIELDS = ["size", "material", "wear"] as const;
const EMPTY: Physical = { size: "", material: "", wear: "" };

/** 真实尺寸 / 材质 / 新旧 of a prop (M5.5, sketch A1): from the bible, editable; the keyframe
 * writes its size against the people in the shot. Saved on blur through `change` (a locked prop
 * shows the impact first). */
export function PropPhysical({
  asset,
  change,
}: {
  asset: Asset;
  change: (p: AssetPatch, done?: string) => void;
}) {
  const { t } = useTranslation("assets");
  const ids = useId();
  const given = { ...EMPTY, ...asset.physical };
  const [typed, setTyped] = useState<Physical>(given);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="grid gap-3 sm:grid-cols-3">
        {FIELDS.map((k) => (
          <div key={k} className="flex flex-col gap-1.5">
            <Label htmlFor={`${ids}-${k}`}>{t(`prop.${k}`)}</Label>
            <Input
              id={`${ids}-${k}`}
              value={typed[k]}
              placeholder={t(`prop.${k}Placeholder`)}
              onChange={(e) => setTyped({ ...typed, [k]: e.target.value })}
              onBlur={() => {
                if (typed[k].trim() !== given[k])
                  change({ physical: { [k]: typed[k] } }, t("prop.saved"));
              }}
            />
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t("prop.hint")}</p>
    </div>
  );
}

/** 比例参考 of a locked prop (M5.5, backend component `scale`, slot `ref_scale`): the prop
 * next to a locked character, drawn once the prop is locked; the keyframe takes it right after
 * the prop's picture. */
export function ScaleReference({ asset, aspect }: { asset: Asset; aspect: Aspect }) {
  const { t } = useTranslation("assets");
  const { t: tc } = useTranslation();
  const { t: tcomp } = useTranslation("components");
  const [zoomed, setZoomed] = useState<number | null>(null);
  const owned = useProducts({ owner: `asset:${asset.id}` });
  const product = owned.data?.find((p) => p.slot === "ref_scale");
  const run = useRunProduct(product?.id ?? "");
  const version = product?.versions.find((v) => v.id === product.adopted_version_id);
  const file = version?.files.find((f) => f.role === "scale");
  const running = product?.status === "queued" || product?.status === "running";
  const who = typeof version?.payload?.character === "string" ? version.payload.character : "";
  const label = t("scale.caption", { name: who });

  return (
    <section aria-label={t("scale.title")} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h3 className="text-sm font-bold">{t("scale.title")}</h3>
        <span className="text-xs text-muted-foreground">
          {running ? t("scale.running") : who ? t("scale.note", { name: who }) : t("scale.none")}
        </span>
      </div>
      {file ? (
        <div className="flex flex-wrap items-end gap-3">
          <figure className="flex shrink-0 flex-col gap-1" style={{ width: CARD_WIDTH[aspect] }}>
            <button
              type="button"
              aria-label={tcomp("lightbox.zoom", { label })}
              title={tcomp("lightbox.zoom", { label })}
              onClick={() => setZoomed(0)}
              className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <MediaThumb
                aspect={aspect}
                seed={`${asset.id}-scale`}
                src={fileUrl(file.sha256)}
                alt={label}
              />
            </button>
            <figcaption className="text-xs text-muted-foreground">{label}</figcaption>
          </figure>
          <div className="flex flex-col items-start gap-1.5">
            <Button
              variant="outline"
              size="sm"
              disabled={running || run.isPending}
              onClick={() =>
                run.mutate(
                  { mode: "rerun" },
                  {
                    onSuccess: () => toast.success(t("scale.redrawing")),
                    onError: (err) => toast.error(errorMessage(tc, err)),
                  },
                )
              }
            >
              <RefreshCw aria-hidden />
              {t("scale.redraw")}
            </Button>
            <p className="text-xs text-muted-foreground">{t("scale.order")}</p>
          </div>
          <MediaLightbox
            items={[{ src: fileUrl(file.sha256), label }]}
            index={zoomed}
            onIndex={setZoomed}
          />
        </div>
      ) : null}
    </section>
  );
}
