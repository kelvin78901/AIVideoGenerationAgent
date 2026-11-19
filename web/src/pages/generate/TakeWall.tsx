import { z } from "zod";
import type { TFunction } from "i18next";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  MicVocal,
  PaintBucket,
  Play,
  Sparkles,
  Star,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { useComponentCatalog } from "@/api/hooks/config";
import {
  useAdoptTake,
  useLipsync,
  usePatchVersion,
  useRequa,
  useUnadopt,
  useUpscale,
} from "@/api/hooks/generate";
import { useRunProduct } from "@/api/hooks/products";
import type { Where } from "@/api/schemas/common";
import type {
  Finishing,
  FinishingRoute,
  Product,
  ProductVersion,
  QaCheck,
} from "@/api/schemas/products";
import type { Shot } from "@/api/schemas/shots";
import type { Aspect } from "@/api/schemas/spec";
import { CostBadge } from "@/components/CostBadge";
import { MediaLightbox, type LightboxItem } from "@/components/MediaLightbox";
import { MediaThumb } from "@/components/MediaThumb";
import { InpaintDialog } from "@/components/pictures/InpaintDialog";
import type { PictureTarget } from "@/components/pictures/RedrawDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TAKE_CARD_WIDTH, TAKE_MEDIA_HEIGHT } from "@/lib/cards";
import { formatPercent, formatTime, formatUsd } from "@/lib/format";
import { qaFails, recommendedTake, takeNote, type TakeStatus } from "@/lib/takes";
import { CheckLines } from "@/pages/storyboard/ShotChecks";
import { cn } from "@/lib/utils";

/** take 检查 (M5.5, ``payload.check``): the contract check of one take. */
const TakeCheckSchema = z.object({
  items: z.array(
    z.object({
      check: z.string(),
      ok: z.boolean(),
      note: z.string(),
      frame: z.number().nullable().optional(),
    }),
  ),
  ok: z.boolean(),
  model: z.string().nullable(),
});

/** A finishing route's model on one side (`local` / `api`): the main one or its `alt`. */
function routeAt(f: Finishing | undefined, where: Where): FinishingRoute | undefined {
  if (f?.where === where) return f;
  return f?.alt?.where === where ? f.alt : undefined;
}

/** About how many minutes a route takes; null when the estimate has no time. */
const minutesOf = (r: FinishingRoute | undefined) =>
  r?.seconds ? Math.max(1, Math.round(r.seconds / 60)) : null;

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
 * 「用 API 出终版」 of a local draft, 局部修复 (lip sync, a region), 2K finishing and 重新质检; a
 * take plays in the lightbox.
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
  episodeId: string | undefined;
}) {
  const { t } = useTranslation("generate");
  const { t: tc } = useTranslation();
  const adopt = useAdoptTake(episodeId);
  const unadopt = useUnadopt(episodeId);
  const rate = usePatchVersion();
  const up = useUpscale();
  const lip = useLipsync();
  const requa = useRequa();
  const run = useRunProduct(product?.id ?? "");
  const [inpaint, setInpaint] = useState<ProductVersion | null>(null);
  const finishing = product?.estimate?.finishing;
  const vinpaint = routeAt(finishing?.vinpaint, "local");
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
    upscale(v: ProductVersion) {
      const route = finishing?.up;
      if (!product || !route) return;
      up.mutate(
        { productId: product.id, versionId: v.id },
        {
          onSuccess: () =>
            toast.success(
              t(route.where === "local" ? "toast.upLocal" : "toast.upApi", {
                ...name(v),
                model: modelName(route.model_key),
                cost: formatUsd(route.cost_usd, { cents: true }),
              }),
            ),
          onError,
        },
      );
    },
    lipsync(v: ProductVersion, where: Where) {
      const route = routeAt(finishing?.lip, where);
      if (!product || !route) return;
      lip.mutate(
        { productId: product.id, versionId: v.id, where },
        {
          onSuccess: () =>
            toast.success(
              t(where === "local" ? "toast.lipLocal" : "toast.lipApi", {
                ...name(v),
                model: modelName(route.model_key),
                cost: formatUsd(route.cost_usd, { cents: true }),
              }),
            ),
          onError,
        },
      );
    },
    requa(v: ProductVersion) {
      if (!product) return;
      requa.mutate(
        { productId: product.id, versionId: v.id },
        { onSuccess: () => toast.info(t("toast.requa", name(v))), onError },
      );
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
              finishing={finishing}
              finalUsd={product.estimate?.final_usd ?? null}
              busy={adopt.isPending || unadopt.isPending}
              finalBusy={run.isPending || running}
              fixBusy={running || lip.isPending || up.isPending}
              onSelect={() => setSelectedId(v.id)}
              onPlay={() => actions.play(v)}
              onFinal={() => actions.final(v)}
              onAdopt={() => actions.adopt(v)}
              onLipsync={(where) => actions.lipsync(v, where)}
              onInpaint={() => setInpaint(v)}
              onUpscale={() => actions.upscale(v)}
              onRequa={() => actions.requa(v)}
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
      <InpaintDialog
        target={inpaint && product ? inpaintTarget(shot, product, inpaint, aspect) : null}
        take={
          inpaint
            ? {
                video: fileOf(inpaint, "video"),
                model: modelName(vinpaint?.model_key),
                minutes: minutesOf(vinpaint),
                textRegions: inpaint.qa?.checks.find((c) => c.metric === "ocr")?.regions,
              }
            : undefined
        }
        onClose={() => setInpaint(null)}
      />
    </section>
  );
}

/** The take as the region dialog paints on it: its first frame. */
function inpaintTarget(
  shot: Shot,
  product: Product,
  v: ProductVersion,
  aspect: Aspect,
): PictureTarget {
  const video = v.files.find((f) => f.role === "video");
  return {
    productId: product.id,
    versionId: v.id,
    idx: 0,
    name: `${shot.label} T${v.n}`,
    src: fileOf(v, "poster"),
    aspect,
    seed: `${shot.label}-${v.n}`,
    w: video?.w ?? null,
    h: video?.h ?? null,
  };
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
    case "speaker":
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
  finishing,
  finalUsd,
  busy,
  finalBusy,
  fixBusy,
  onSelect,
  onPlay,
  onFinal,
  onAdopt,
  onLipsync,
  onInpaint,
  onUpscale,
  onRequa,
}: {
  shot: Shot;
  product: Product;
  version: ProductVersion;
  aspect: Aspect;
  recommended: boolean;
  selected: boolean;
  modelName: (key: string | null | undefined) => string;
  /** What finishing a take costs on each route (`up`, `lip`, `vinpaint`; the estimate's). */
  finishing: Record<string, Finishing> | undefined;
  /** What 「用 API 出终版」 of a take costs (the backend's estimate); null: none. */
  finalUsd: number | null;
  busy: boolean;
  finalBusy: boolean;
  /** A run on this shot is under way: no repair or finishing until it is done. */
  fixBusy: boolean;
  onSelect: () => void;
  onPlay: () => void;
  onFinal: () => void;
  onAdopt: () => void;
  onLipsync: (where: Where) => void;
  onInpaint: () => void;
  onUpscale: () => void;
  onRequa: () => void;
}) {
  const { t } = useTranslation("generate");
  const { t: te } = useTranslation("enums");
  const adopted = v.id === product.adopted_version_id;
  const failed = qaFails(v);
  const fails = failed.length;
  const onlyLips = fails === 1 && failed[0]?.metric === "lipsync";
  const [itemsOpen, setItemsOpen] = useState(false);
  const policy = v.qa?.policy?.action;
  const upscale = finishing?.up;
  // take 检查 (M5.5): what the contract check found; only a warning (sketch T1).
  const checked = TakeCheckSchema.safeParse(v.payload.check);
  const check = checked.success ? checked.data : null;
  const checkFails = check ? check.items.filter((x) => !x.ok).length : 0;
  const sheet = v.files.find((f) => f.role === "sheet");
  // 检查没过自动重画 (M5.5 9e-5): how many more tries this take took.
  const redraws = typeof v.payload.redraws === "number" ? v.payload.redraws : 0;
  const note = takeNote(product, v);
  const noteText = note
    ? note.n === undefined
      ? t(`note.${note.key}`, { n: "?" })
      : t(`note.${note.key}`, { n: note.n })
    : null;
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
                ) : fails ? (
                  <span className="absolute top-2 right-2 rounded bg-tone-warn-bg px-1.5 py-0.5 text-[11px] text-tone-warn-fg">
                    {onlyLips ? t("wall.onlyLips") : t("wall.failN", { count: fails })}
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
        {noteText ? <div className="text-xs text-tone-warn-fg">{noteText}</div> : null}
      </div>
      {v.qa ? (
        <div className="flex flex-col gap-1 rounded-lg bg-muted/60 px-2.5 py-2">
          <div className="flex items-center text-xs font-bold">
            <span className="flex-1">{t("wall.qa")}</span>
            <span className={fails ? "text-tone-warn-fg" : "text-tone-info-fg"}>
              {fails ? t("wall.failN", { count: fails }) : t("wall.pass")}
            </span>
          </div>
          {v.qa.checks.map((c) => {
            const items = c.metric === "vlm" ? (c.items ?? []) : [];
            return (
              <div key={c.metric} className="flex flex-col gap-1">
                <div className="flex items-center gap-2 text-xs">
                  {items.length ? (
                    <button
                      type="button"
                      aria-expanded={itemsOpen}
                      aria-label={t(itemsOpen ? "wall.hideItems" : "wall.showItems")}
                      onClick={() => setItemsOpen((open) => !open)}
                      className="flex flex-1 items-center gap-0.5 text-left text-muted-foreground hover:text-foreground"
                    >
                      {t(`qa.${c.metric}`)}
                      {itemsOpen ? (
                        <ChevronDown className="size-3" aria-hidden />
                      ) : (
                        <ChevronRight className="size-3" aria-hidden />
                      )}
                    </button>
                  ) : (
                    <span className="flex-1 text-muted-foreground">{t(`qa.${c.metric}`)}</span>
                  )}
                  <span className="font-mono">{qaValue(t, te, c)}</span>
                  <span
                    className={cn(
                      "w-11 text-right font-medium",
                      c.ok === null || c.off
                        ? "text-muted-foreground"
                        : c.ok
                          ? "text-tone-info-fg"
                          : "text-tone-warn-fg",
                    )}
                  >
                    {t(
                      c.off
                        ? "wall.off"
                        : c.ok === null
                          ? "wall.na"
                          : c.ok
                            ? "wall.pass"
                            : "wall.fail",
                    )}
                  </span>
                </div>
                {items.length && itemsOpen ? (
                  <div className="flex flex-col gap-1 border-l-2 pl-2">
                    <CheckLines items={items} />
                    {sheet ? (
                      <img
                        src={fileUrl(sheet.sha256)}
                        alt={t("wall.sheet")}
                        className="w-full rounded border"
                      />
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
          {policy && policy !== "none" ? (
            <span className="text-xs text-muted-foreground">
              {t(`policy.${policy}`, { model: modelName(v.qa.policy?.model) })}
            </span>
          ) : null}
          <button
            type="button"
            disabled={fixBusy}
            onClick={onRequa}
            className="self-start text-xs text-primary hover:underline disabled:text-muted-foreground disabled:no-underline"
          >
            {t("wall.requa")}
          </button>
        </div>
      ) : check ? (
        <div
          role="group"
          aria-label={t("wall.check")}
          className="flex flex-col gap-1 rounded-lg bg-muted/60 px-2.5 py-2"
        >
          <div className="flex items-center text-xs font-bold">
            <span className="flex-1">{t("wall.check")}</span>
            <StatusBadge tone={checkFails ? "warn" : "pass"} icon={null}>
              {checkFails ? t("wall.checkFails", { count: checkFails }) : t("wall.checkOk")}
            </StatusBadge>
          </div>
          <CheckLines items={check.items} />
          {redraws ? (
            <span className="text-xs text-muted-foreground">
              {t(checkFails ? "wall.redrawnStill" : "wall.redrawn", { count: redraws })}
            </span>
          ) : null}
          {checkFails && sheet ? (
            <img
              src={fileUrl(sheet.sha256)}
              alt={t("wall.sheet")}
              className="w-full rounded border"
            />
          ) : null}
          <button
            type="button"
            disabled={fixBusy}
            onClick={onRequa}
            className="self-start text-xs text-primary hover:underline disabled:text-muted-foreground disabled:no-underline"
          >
            {t("wall.requa")}
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-lg bg-muted/60 px-2.5 py-2 text-xs">
          <span className="flex-1 font-bold">{t("wall.qa")}</span>
          <span className="text-muted-foreground">{t("wall.unchecked")}</span>
          <button
            type="button"
            disabled={fixBusy}
            onClick={onRequa}
            className="text-primary hover:underline disabled:text-muted-foreground disabled:no-underline"
          >
            {t("wall.requa")}
          </button>
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
        <FixMenu
          shot={shot}
          finishing={finishing}
          modelName={modelName}
          disabled={fixBusy}
          onLipsync={onLipsync}
          onInpaint={onInpaint}
        />
        <Button size="sm" variant="outline" disabled={!upscale || fixBusy} onClick={onUpscale}>
          {t("wall.upscale", {
            cost: !upscale
              ? "…"
              : upscale.where === "local"
                ? t("wall.upLocal")
                : formatUsd(upscale.cost_usd, { cents: true }),
          })}
        </Button>
      </div>
    </li>
  );
}

function FixItem({
  icon,
  label,
  hint,
  reason,
  onSelect,
}: {
  icon: ReactNode;
  label: string;
  hint: string | undefined;
  /** Why it cannot run; it is greyed with the reason written out. */
  reason: string | undefined;
  onSelect: () => void;
}) {
  return (
    <DropdownMenuItem className="min-h-9 gap-2" disabled={!!reason} onSelect={onSelect}>
      {icon}
      <span className="flex grow flex-col">
        {label}
        {reason ? <span className="text-xs text-muted-foreground">{reason}</span> : null}
      </span>
      {hint && !reason ? <small className="text-xs text-muted-foreground">{hint}</small> : null}
    </DropdownMenuItem>
  );
}

/**
 * 局部修复 ▾ (草图 G1): 口型修复 on the route's local model and on its API one, each with its
 * price or time, and 涂一块区域重画… (视频局部修复, only locally). What this machine cannot
 * run is greyed with the reason; lip sync needs someone speaking on screen.
 */
function FixMenu({
  shot,
  finishing,
  modelName,
  disabled,
  onLipsync,
  onInpaint,
}: {
  shot: Shot;
  finishing: Record<string, Finishing> | undefined;
  modelName: (key: string | null | undefined) => string;
  disabled: boolean;
  onLipsync: (where: Where) => void;
  onInpaint: () => void;
}) {
  const { t } = useTranslation("generate");
  const { t: tk } = useTranslation("components");
  const components = useComponentCatalog().data?.components;
  const blocked = (id: string, where: Where): string | undefined => {
    const def = components?.find((c) => c.id === id);
    const why = def?.unavailable[where];
    if (why)
      return tk(`picker.unavailable.${why.code}` as "picker.unavailable.machine", why.params);
    const models = where === "local" ? def?.local_models : def?.api_models;
    if (def && !models?.length)
      return tk(
        where === "local" ? "picker.unavailable.no_local_model" : "picker.unavailable.no_api_model",
      );
    return undefined;
  };
  const hint = (r: FinishingRoute | undefined) => {
    if (!r) return undefined;
    if (r.where === "api")
      return t("wall.routeApi", {
        model: modelName(r.model_key),
        cost: formatUsd(r.cost_usd, { cents: true }),
      });
    const minutes = minutesOf(r);
    return minutes ? t("wall.routeLocal", { minutes }) : t("wall.routeLocalPlain");
  };
  const speaks = !!shot.dialogue;
  const lipRows = (["local", "api"] as const).flatMap((where) => {
    const route = routeAt(finishing?.lip, where);
    const why = blocked("lip", where);
    if (!route && !why) return [];
    return [{ where, route, reason: speaks ? why : t("wall.noDialogue") }];
  });
  const vinpaint = routeAt(finishing?.vinpaint, "local");
  const vinpaintWhy = blocked("vinpaint", "local");

  return (
    // Not modal: a modal menu that opens a dialog leaves `pointer-events: none` on the body.
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild disabled={disabled}>
        <Button size="sm" variant="outline">
          {t("wall.fix")}
          <ChevronDown aria-hidden className="size-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-80 p-1.5">
        {lipRows.map((row) => (
          <FixItem
            key={row.where}
            icon={<MicVocal className="size-4" aria-hidden />}
            label={t(row.where === "local" ? "wall.lip" : "wall.lipApi")}
            hint={hint(row.route)}
            reason={row.reason}
            onSelect={() => onLipsync(row.where)}
          />
        ))}
        {lipRows.length ? <DropdownMenuSeparator /> : null}
        <FixItem
          icon={<PaintBucket className="size-4" aria-hidden />}
          label={t("wall.vinpaint")}
          hint={hint(vinpaint)}
          reason={vinpaintWhy ?? (vinpaint ? undefined : tk("picker.unavailable.no_local_model"))}
          onSelect={onInpaint}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
