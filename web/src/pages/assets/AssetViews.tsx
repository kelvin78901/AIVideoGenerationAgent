import { useState } from "react";
import { useTranslation } from "react-i18next";

import { fileUrl } from "@/api/client";
import { useProducts } from "@/api/hooks/products";
import type { Asset } from "@/api/schemas/assets";
import type { Aspect } from "@/api/schemas/spec";
import { MediaLightbox } from "@/components/MediaLightbox";
import { MediaThumb } from "@/components/MediaThumb";
import { CARD_WIDTH } from "@/pages/assets/status";

const VIEWS = ["side", "back", "expressions"] as const;

/** 补视图 of a character: side, back and expressions, drawn from the locked picture once it is
 * locked (backend component `views`, adopted on every run). */
export function AssetViews({ asset, aspect }: { asset: Asset; aspect: Aspect }) {
  const { t } = useTranslation("assets");
  const { t: tc } = useTranslation("components");
  const [zoomed, setZoomed] = useState<number | null>(null);
  const owned = useProducts({ owner: `asset:${asset.id}` });
  const product = owned.data?.find((p) => p.slot === "ref_views");
  const version = product?.versions.find((v) => v.id === product.adopted_version_id);
  const running = product?.status === "queued" || product?.status === "running";
  const stale = product?.status === "stale";
  const files = version?.files.filter((f) => f.role === "view") ?? [];
  const pictures = VIEWS.flatMap((view) => {
    const f = files.find((x) => x.view === view);
    return f ? [{ src: fileUrl(f.sha256), label: t(`views.${view}`), view }] : [];
  });

  return (
    <section aria-label={t("views.title")} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h3 className="text-sm font-bold">{t("views.title")}</h3>
        <span className="text-xs text-muted-foreground">
          {running ? t("views.running") : stale ? t("views.stale") : t("views.note")}
        </span>
      </div>
      {files.length ? (
        <div className="flex flex-wrap gap-3">
          {VIEWS.map((view) => {
            const f = files.find((x) => x.view === view);
            const name = t(`views.${view}`);
            const at = pictures.findIndex((p) => p.view === view);
            return (
              <figure
                key={view}
                className="flex shrink-0 flex-col gap-1"
                style={{ width: CARD_WIDTH[aspect] }}
              >
                {f ? (
                  <button
                    type="button"
                    aria-label={tc("lightbox.zoom", { label: name })}
                    title={tc("lightbox.zoom", { label: name })}
                    onClick={() => setZoomed(at)}
                    className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <MediaThumb
                      aspect={aspect}
                      seed={`${asset.id}-${view}`}
                      src={fileUrl(f.sha256)}
                      alt={name}
                    />
                  </button>
                ) : (
                  <MediaThumb aspect={aspect} seed={`${asset.id}-${view}`} alt={name} dashed />
                )}
                <figcaption className="text-xs text-muted-foreground">{name}</figcaption>
              </figure>
            );
          })}
          <MediaLightbox items={pictures} index={zoomed} onIndex={setZoomed} />
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {running ? t("views.running") : t("views.none")}
        </p>
      )}
    </section>
  );
}
