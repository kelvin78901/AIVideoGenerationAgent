import type { TFunction } from "i18next";
import { Loader2, Play, Sparkles, Star } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { useAdoptTake, usePatchVersion, useUnadopt, useUpscale } from "@/api/hooks/generate";
import { useRunProduct } from "@/api/hooks/products";
import type { Where } from "@/api/schemas/common";
import type { Product, ProductVersion, QaCheck } from "@/api/schemas/products";
import type { Shot } from "@/api/schemas/shots";
import type { Aspect } from "@/api/schemas/spec";
import { CostBadge } from "@/components/CostBadge";
import { MediaLightbox, type LightboxItem } from "@/components/MediaLightbox";
import { MediaThumb } from "@/components/MediaThumb";
import { Button } from "@/components/ui/button";
import { TAKE_CARD_WIDTH, TAKE_MEDIA_HEIGHT } from "@/lib/cards";
import { formatPercent, formatTime, formatUsd } from "@/lib/format";
import { qaFails, recommendedTake, takeNote, type TakeStatus } from "@/lib/takes";
import { cn } from "@/lib/utils";

/** Where 2K finishing runs and what one take costs there (the 「2K 精修 · …」 button). */
export interface UpscaleRoute {
  model: string;
  where: Where;
  costUsd: number;
}

const editable = (el: EventTarget | null) =>
  el instanceof HTMLElement &&
  (el.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) ||
    !!el.closest("[role=menu],[role=dialog],[role=listbox]"));

/** A take's file of a role (`video`, `poster`) as a URL. */
const fileOf = (v: ProductVersion, role: string) => {
  const f = v.files.find((x) => x.role === role);
  return f ? fileUrl(f.sha256) : null;
};

/** A local H3 draft: 「用 API 出终版」 regenerates it at 2K (Regenerate-2K takes H3's own drafts). */
const regenerable = (v: ProductVersion) =>
  v.stage === "draft" && v.where === "local" && !!v.model_key?.includes("h3");

/**
 * 候选墙 for one shot: each take with its QA, the recommended pick, adopt (one per shot),
 * 「用 API 出终版」 of a local draft, region fix and 2K finishing; a take plays in the lightbox.
 * Keys: ← → move, Space play, 1–5 rate, A adopt.
 */
export function TakeWall({
  shot,
  shots,
  status,
  product,
  aspect,
  queuePos,
  textInPost,
  modelName,
  upscale,
  episodeId,
}: {
  shot: Shot;
  shots: Shot[];
  status: TakeStatus;
  product: Product | undefined;
  aspect: Aspect;
  /** 1-based place in the local queue while status is `queued`. */
  queuePos: number;
  /** The shot's on-screen text is pasted in post, so takes are made without it. */
  textInPost: boolean;
  modelName: (key: string | null | undefined) => string;
  upscale: UpscaleRoute | undefined;
  episodeId: string | undefined;
}) {
  const { t } = useTranslation("generate");
  const { t: tc } = useTranslation();
  const adopt = useAdoptTake(episodeId);
  const unadopt = useUnadopt(episodeId);
  const rate = usePatchVersion();
  const up = useUpscale();
  const run = useRunProduct(product?.id ?? "");
  const takes = product?.versions ?? [];
  const [playing, setPlaying] = useState<number | null>(null);
  const clips: LightboxItem[] = takes.map((v) => ({
    src: fileOf(v, "poster") ?? "",
    video: fileOf(v, "video") ?? undefined,
    label: t("wall.clip", { id: shot.label, n: v.n, model: modelName(v.model_key) }),
  }));
  const rec = product ? recommendedTake(product) : undefined;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected =
    takes.find((v) => v.id === selectedId) ??
    rec ??
    takes.find((v) => v.id === product?.adopted_version_id) ??
    takes.at(-1);
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const name = (v: ProductVersion) => ({ id: shot.label, n: v.n });

  const actions = {
    adopt(v: ProductVersion) {
      if (!product) return;
      if (v.id === product.adopted_version_id) {
        unadopt.mutate(product.id, {
          onSuccess: () => toast.success(t("toast.unadopted", name(v))),
          onError,
        });
        return;
      }
      const fails = qaFails(v).length;
      const next = shots.find((s) => s.tail_from === shot.label);
      const firstAdoption = !product.adopted_version_id;
      adopt.mutate(v.id, {
        onSuccess: () =>
          toast.success(
            t(fails ? "toast.adoptedWarn" : "toast.adopted", { ...name(v), fails }) +
              (next && firstAdoption ? t("toast.unblocked", { id: next.label }) : ""),
          ),
        onError,
      });
    },
    play: (v: ProductVersion) => {
      const i = takes.findIndex((x) => x.id === v.id);
      if (i >= 0 && clips[i]?.video) setPlaying(i);
    },
    final(v: ProductVersion) {
      run.mutate(
        { mode: "run", where: "api", params: { source_version_id: v.id } },
        { onSuccess: () => toast.info(t("toast.final", name(v))), onError },
      );
    },
    fix: () => toast.info(t("toast.fix")),
    upscale(v: ProductVersion) {
      if (!upscale) return;
      up.mutate(v.id, {
        onSuccess: () =>
          toast.success(
            t(upscale.where === "local" ? "toast.upLocal" : "toast.upApi", {
              ...name(v),
              model: modelName(upscale.model),
              cost: formatUsd(upscale.costUsd, { cents: true }),
            }),
          ),
        onError,
      });
    },
    rate(v: ProductVersion, stars: number) {
      rate.mutate(
        { id: v.id, patch: { rating: stars } },
        { onSuccess: () => toast.success(t("toast.rated", { ...name(v), stars })), onError },
      );
    },
  };

  // Keyboard on the whole page while no field, menu or dialog has focus.
  const adoptedId = product?.adopted_version_id;
  const live = useRef({ takes, selected, actions, adoptedId });
  useEffect(() => {
    live.current = { takes, selected, actions, adoptedId };
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || editable(e.target)) return;
      const { takes: list, selected: cur, actions: act, adoptedId: adopted } = live.current;
      if (!cur) return;
      const i = list.findIndex((v) => v.id === cur.id);
      const onButton = e.target instanceof HTMLElement && !!e.target.closest("button,a");
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        const next = list[i + (e.key === "ArrowLeft" ? -1 : 1)];
        if (!next) return;
        e.preventDefault();
        setSelectedId(next.id);
        document.getElementById(`take-${next.id}`)?.scrollIntoView?.({ block: "nearest" });
      } else if (e.key === " " && !onButton) {
        e.preventDefault();
        act.play(cur);
      } else if (/^[1-5]$/.test(e.key)) {
        act.rate(cur, Number(e.key));
      } else if (e.key === "a" || e.key === "A") {
        if (cur.id !== adopted) act.adopt(cur);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const running = product?.status === "running";

  return (
    <section aria-labelledby="take-wall-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="take-wall-title" className="text-lg font-bold">
          {t("wall.title", { id: shot.label })}
        </h2>
        <span className="text-sm text-muted-foreground">{shot.summary}</span>
        {takes.length ? (
          <span className="ml-auto text-xs text-muted-foreground">{t("wall.keys")}</span>
        ) : null}
      </div>
      {product && takes.length ? (
        <ul aria-label={t("wall.label")} className="flex flex-wrap items-start gap-3.5">
          {takes.map((v) => (
            <TakeCard
              key={v.id}
              shot={shot}
              product={product}
              version={v}
              aspect={aspect}
              recommended={v.id === rec?.id}
              selected={v.id === selected?.id}
              modelName={modelName}
              upscale={upscale}
              finalUsd={product.estimate?.final_usd ?? null}
              busy={adopt.isPending || unadopt.isPending}
              finalBusy={run.isPending || running}
              onSelect={() => setSelectedId(v.id)}
              onPlay={() => actions.play(v)}
              onFinal={() => actions.final(v)}
              onAdopt={() => actions.adopt(v)}
              onFix={actions.fix}
              onUpscale={() => actions.upscale(v)}
            />
          ))}
          {running ? (
            <li
              style={{ width: TAKE_CARD_WIDTH[aspect] }}
              className="flex min-h-72 flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-primary/40 bg-primary/5 p-4 text-center text-primary"
            >
              <Loader2 className="size-5 animate-spin" aria-hidden />
              <span className="text-sm font-medium">{t("wall.generating")}</span>
              <span className="text-xs">{modelName(product?.running?.model_key)}</span>
            </li>
          ) : null}
        </ul>
      ) : (
        <div className="rounded-xl border border-dashed bg-card px-4 py-8 text-center text-sm leading-relaxed text-muted-foreground">
          <EmptyText
            shot={shot}
            status={status}
            product={product}
            pos={queuePos}
            textInPost={textInPost}
            modelName={modelName}
          />
        </div>
      )}
      <MediaLightbox items={clips} index={playing} onIndex={setPlaying} />
    </section>
  );
}

function EmptyText({
  shot,
  status,
  product,
  pos,
  textInPost,
  modelName,
}: {
  shot: Shot;
  status: TakeStatus;
  product: Product | undefined;
  pos: number;
  textInPost: boolean;
  modelName: (key: string | null | undefined) => string;
}) {
  const { t } = useTranslation("generate");
  if (status === "running")
    return t("empty.running", {
      model: modelName(product?.running?.model_key),
      n: (product?.versions.length ?? 0) + 1,
    });
  if (status === "waiting") return t("empty.waiting", { id: shot.tail_from });
  if (status !== "queued") return t("empty.none");
  const extra = [
    shot.dialogue && shot.audio_mode === "tts" ? t("empty.queuedDub") : null,
    textInPost ? t("empty.queuedText") : null,
  ].filter(Boolean);
  return [t("empty.queued", { pos }), ...extra].join("");
}

function qaValue(t: TFunction<"generate">, te: TFunction<"enums">, c: QaCheck): string {
  if (c.ok === null) return "—";
  switch (c.metric) {
    case "face":
      return c.value?.toFixed(2) ?? "—";
    case "lipsync":
      return c.value?.toFixed(1) ?? "—";
    case "asr":
      return c.value === null ? "—" : formatPercent(c.value, 0);
    case "ocr":
      return c.ok ? t("wall.exact") : (c.text ?? te(`qaIssue.${c.issue ?? "text_mismatch"}`));
    case "vlm":
      return c.ok ? t("wall.noIssue") : (c.text ?? (c.issue ? te(`qaIssue.${c.issue}`) : "—"));
  }
}

function TakeCard({
  shot,
  product,
  version: v,
  aspect,
  recommended,
  selected,
  modelName,
  upscale,
  finalUsd,
  busy,
  finalBusy,
  onSelect,
  onPlay,
  onFinal,
  onAdopt,
  onFix,
  onUpscale,
}: {
  shot: Shot;
  product: Product;
  version: ProductVersion;
  aspect: Aspect;
  recommended: boolean;
  selected: boolean;
  modelName: (key: string | null | undefined) => string;
  upscale: UpscaleRoute | undefined;
  /** What 「用 API 出终版」 of a take costs (the backend's estimate); null: none. */
  finalUsd: number | null;
  busy: boolean;
  finalBusy: boolean;
  onSelect: () => void;
  onPlay: () => void;
  onFinal: () => void;
  onAdopt: () => void;
  onFix: () => void;
  onUpscale: () => void;
}) {
  const { t } = useTranslation("generate");
  const { t: te } = useTranslation("enums");
  const adopted = v.id === product.adopted_version_id;
  const fails = qaFails(v).length;
  const note = takeNote(product, v);
  const take = t("wall.take", { n: v.n });
  const res = typeof v.payload.resolution === "string" ? v.payload.resolution : "768p";
  const poster = fileOf(v, "poster");
  const playable = !!fileOf(v, "video");
  const portrait = aspect === "9:16" || aspect === "3:4";
  const [rw = 9, rh = 16] = aspect.split(":").map(Number);
  const seconds = typeof v.payload.duration_s === "number" ? v.payload.duration_s : shot.duration_s;

  return (
    <li
      id={`take-${v.id}`}
      aria-label={t("wall.takeLabel", { n: v.n })}
      aria-current={selected || undefined}
      onClick={onSelect}
      style={{ width: TAKE_CARD_WIDTH[aspect] }}
      className={cn(
        "flex flex-col gap-2.5 rounded-xl border-2 bg-card p-2.5",
        adopted ? "border-foreground" : recommended ? "border-primary" : "border-border",
        selected && "ring-2 ring-ring ring-offset-2 ring-offset-background",
      )}
    >
      <div
        className="flex justify-center rounded-md bg-media"
        style={portrait ? { height: TAKE_MEDIA_HEIGHT } : undefined}
      >
        <div style={{ width: portrait ? Math.round((TAKE_MEDIA_HEIGHT * rw) / rh) : "100%" }}>
          <MediaThumb
            aspect={aspect}
            seed={`${shot.label}-${v.n}`}
            src={poster}
            alt={t("wall.posterAlt", { n: v.n })}
            overlay={
              <>
                <span className="absolute top-2 left-2 rounded bg-white px-1.5 py-0.5 font-mono text-xs text-neutral-900">
                  {take}
                </span>
                {adopted ? (
                  <span className="absolute top-2 right-2 rounded bg-neutral-900 px-1.5 py-0.5 text-[11px] text-white">
                    {t("wall.adopted")}
                  </span>
                ) : recommended ? (
                  <span className="absolute top-2 right-2 rounded bg-primary px-1.5 py-0.5 text-[11px] text-primary-foreground">
                    {t("wall.recommended")}
                  </span>
                ) : null}
                <span className="absolute bottom-2 left-2 rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-neutral-900">
                  {t("wall.meta", { seconds: Math.round(seconds * 10) / 10, res })}
                </span>
                {v.rating ? (
                  <span
                    className="absolute right-2 bottom-2 flex items-center gap-0.5 rounded bg-white px-1.5 py-0.5 text-[11px] text-neutral-900"
                    title={t("wall.rating", { n: v.rating })}
                  >
                    <Star className="size-3 fill-current" aria-hidden />
                    {t("wall.rating", { n: v.rating })}
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={onPlay}
                  disabled={!playable}
                  aria-label={t("wall.play", { n: v.n })}
                  className="absolute top-1/2 left-1/2 flex size-13 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-neutral-900 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Play className="size-4.5 fill-current" aria-hidden />
                </button>
              </>
            }
          />
        </div>
      </div>
      <div className="flex flex-col gap-0.5">
        <div className="text-sm font-medium">{modelName(v.model_key)}</div>
        <div className="text-xs text-muted-foreground">
          {v.where ? te(`where.${v.where}`) : ""} ·{" "}
          <CostBadge where={v.where ?? "api"} usd={v.cost_usd} className="text-inherit" /> ·{" "}
          {formatTime(v.created_at)}
        </div>
        {note ? <div className="text-xs text-tone-warn-fg">{t(`note.${note}`)}</div> : null}
      </div>
      {v.qa ? (
        <div className="flex flex-col gap-1 rounded-lg bg-muted/60 px-2.5 py-2">
          <div className="flex items-center text-xs font-bold">
            <span className="flex-1">{t("wall.qa")}</span>
            <span className={fails ? "text-tone-warn-fg" : "text-tone-info-fg"}>
              {fails ? t("wall.failN", { count: fails }) : t("wall.pass")}
            </span>
          </div>
          {v.qa.checks.map((c) => (
            <div key={c.metric} className="flex items-center gap-2 text-xs">
              <span className="flex-1 text-muted-foreground">{t(`qa.${c.metric}`)}</span>
              <span className="font-mono">{qaValue(t, te, c)}</span>
              <span
                className={cn(
                  "w-11 text-right font-medium",
                  c.ok === null
                    ? "text-muted-foreground"
                    : c.ok
                      ? "text-tone-info-fg"
                      : "text-tone-warn-fg",
                )}
              >
                {t(c.ok === null ? "wall.na" : c.ok ? "wall.pass" : "wall.fail")}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex items-center rounded-lg bg-muted/60 px-2.5 py-2 text-xs">
          <span className="flex-1 font-bold">{t("wall.qa")}</span>
          <span className="text-muted-foreground">{t("wall.unchecked")}</span>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {regenerable(v) && finalUsd !== null && !product.locked_hash ? (
          <Button size="sm" variant="outline" disabled={finalBusy} onClick={onFinal}>
            <Sparkles aria-hidden />
            {t("wall.final", { cost: formatUsd(finalUsd, { cents: true }) })}
          </Button>
        ) : null}
        <Button
          size="sm"
          variant={adopted ? "outline" : "default"}
          disabled={busy || product.locked_hash !== null}
          onClick={onAdopt}
        >
          {t(adopted ? "wall.unadopt" : "wall.adopt")}
        </Button>
        <Button size="sm" variant="outline" onClick={onFix}>
          {t("wall.fix")}
        </Button>
        <Button size="sm" variant="outline" disabled={!upscale} onClick={onUpscale}>
          {t("wall.upscale", {
            cost: !upscale
              ? "…"
              : upscale.where === "local"
                ? t("wall.upLocal")
                : formatUsd(upscale.costUsd, { cents: true }),
          })}
        </Button>
      </div>
    </li>
  );
}
