import { RefreshCw, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { useReplaceView } from "@/api/hooks/pictures";
import { useProducts } from "@/api/hooks/products";
import type { Asset } from "@/api/schemas/assets";
import type { Aspect } from "@/api/schemas/spec";
import { MediaLightbox } from "@/components/MediaLightbox";
import { MediaThumb } from "@/components/MediaThumb";
import { Button } from "@/components/ui/button";
import { CARD_WIDTH } from "@/lib/cards";

/** The views a version lists (`payload.views`), in its order; versions before 2026-10-21 have
 * one `expressions` sheet where newer ones have four expressions, one a picture. */
const KNOWN = ["side", "back", "calm", "smile", "angry", "sad", "expressions"] as const;
type View = (typeof KNOWN)[number];
const VIEWS: View[] = ["side", "back", "calm", "smile", "angry", "sad"];

const isView = (v: unknown): v is View => KNOWN.includes(v as View);

function viewsOf(payload: Record<string, unknown> | undefined): View[] {
  const listed = payload?.views;
  return Array.isArray(listed) && listed.length > 0 && listed.every(isView) ? listed : VIEWS;
}

/** 补视图 of a character: side, back and four expressions, drawn from the locked picture once it
 * is locked (backend component `views`, adopted on every run). Each one can be drawn again or
 * replaced by an upload (草图 A3): a new version of the set, the other five copied. */
export function AssetViews({ asset, aspect }: { asset: Asset; aspect: Aspect }) {
  const { t } = useTranslation("assets");
  const { t: tc } = useTranslation("components");
  const { t: tcommon } = useTranslation();
  const [zoomed, setZoomed] = useState<number | null>(null);
  const replace = useReplaceView(asset.id);
  const input = useRef<HTMLInputElement>(null);
  // The view an upload is for, while the file picker is open.
  const [uploading, setUploading] = useState<View | null>(null);
  const owned = useProducts({ owner: `asset:${asset.id}` });
  const product = owned.data?.find((p) => p.slot === "ref_views");
  const version = product?.versions.find((v) => v.id === product.adopted_version_id);
  const running = product?.status === "queued" || product?.status === "running";
  const stale = product?.status === "stale";
  const files = version?.files.filter((f) => f.role === "view") ?? [];
  const views = viewsOf(version?.payload);
  const pictures = views.flatMap((view) => {
    const f = files.find((x) => x.view === view);
    return f ? [{ src: fileUrl(f.sha256), label: t(`views.${view}`), view }] : [];
  });
  // The old single 表情 sheet is not one of the views a set can swap.
  const swappable = (view: View) => !!product && view !== "expressions";
  const busy = running || replace.isPending;
  const fail = (err: unknown) => toast.error(errorMessage(tcommon, err));
  const redraw = (view: View) =>
    product &&
    replace.mutate(
      { productId: product.id, view },
      {
        onSuccess: () => toast.info(t("views.redrawStarted", { view: t(`views.${view}`) })),
        onError: fail,
      },
    );

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
          {views.map((view) => {
            const f = files.find((x) => x.view === view);
            const name = t(`views.${view}`);
            const at = pictures.findIndex((p) => p.view === view);
            return (
              <figure
                key={view}
                className="group flex shrink-0 flex-col gap-1"
                style={{ width: CARD_WIDTH[aspect] }}
              >
                <div className="relative">
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
                  {swappable(view) ? (
                    // Shown on hover and on keyboard focus (草图 A3 「悬停一张：换一张」).
                    <div className="absolute inset-x-1 bottom-1 flex flex-wrap justify-center gap-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
                      <Button
                        size="sm"
                        variant="secondary"
                        className="h-7 px-2 text-xs"
                        // An outdated set is drawn again whole (409 `views_outdated`).
                        disabled={busy || stale}
                        title={stale ? t("views.stale") : undefined}
                        aria-label={t("views.redrawOne", { view: name })}
                        onClick={() => redraw(view)}
                      >
                        <RefreshCw aria-hidden className="size-3.5" />
                        {t("views.redraw")}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        className="h-7 px-2 text-xs"
                        disabled={busy}
                        aria-label={t("views.uploadOne", { view: name })}
                        onClick={() => {
                          setUploading(view);
                          input.current?.click();
                        }}
                      >
                        <Upload aria-hidden className="size-3.5" />
                        {t("views.upload")}
                      </Button>
                    </div>
                  ) : null}
                </div>
                <figcaption className="text-xs text-muted-foreground">{name}</figcaption>
              </figure>
            );
          })}
          <MediaLightbox items={pictures} index={zoomed} onIndex={setZoomed} />
          <input
            ref={input}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            aria-label={t("views.uploadFile")}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              const view = uploading;
              setUploading(null);
              if (file && view && product)
                replace.mutate(
                  { productId: product.id, view, file },
                  {
                    onSuccess: () =>
                      toast.success(t("views.uploaded", { view: t(`views.${view}`) })),
                    onError: fail,
                  },
                );
            }}
          />
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {running ? t("views.running") : t("views.none")}
        </p>
      )}
    </section>
  );
}
