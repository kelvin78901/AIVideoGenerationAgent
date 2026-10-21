import { useTranslation } from "react-i18next";

import { fileUrl } from "@/api/client";
import { useProducts } from "@/api/hooks/products";
import type { Asset } from "@/api/schemas/assets";
import type { Aspect } from "@/api/schemas/spec";
import { MediaThumb } from "@/components/MediaThumb";

const VIEWS = ["side", "back", "expressions"] as const;

/** 补视图 of a character: side, back and expressions, drawn from the locked picture once it is
 * locked (backend component `views`, adopted on every run). */
export function AssetViews({ asset, aspect }: { asset: Asset; aspect: Aspect }) {
  const { t } = useTranslation("assets");
  const owned = useProducts({ owner: `asset:${asset.id}` });
  const product = owned.data?.find((p) => p.slot === "ref_views");
  const version = product?.versions.find((v) => v.id === product.adopted_version_id);
  const running = product?.status === "queued" || product?.status === "running";
  const stale = product?.status === "stale";
  const files = version?.files.filter((f) => f.role === "view") ?? [];

  return (
    <section aria-label={t("views.title")} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h3 className="text-sm font-bold">{t("views.title")}</h3>
        <span className="text-xs text-muted-foreground">
          {running ? t("views.running") : stale ? t("views.stale") : t("views.note")}
        </span>
      </div>
      {files.length ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {VIEWS.map((view) => {
            const f = files.find((x) => x.view === view);
            return (
              <figure key={view} className="flex flex-col gap-1">
                <MediaThumb
                  aspect={aspect}
                  seed={`${asset.id}-${view}`}
                  src={f ? fileUrl(f.sha256) : null}
                  alt={t(`views.${view}`)}
                  dashed={!f}
                />
                <figcaption className="text-xs text-muted-foreground">
                  {t(`views.${view}`)}
                </figcaption>
              </figure>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {running ? t("views.running") : t("views.none")}
        </p>
      )}
    </section>
  );
}
