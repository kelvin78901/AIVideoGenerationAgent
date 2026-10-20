/** 成片规格 (prototype Spec.dc.html; SPEC 13). */
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Lock } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useComponentCatalog } from "@/api/hooks/config";
import { useImpactPreview } from "@/api/hooks/impact";
import {
  seriesKeys,
  useEpisodes,
  useOutputSpec,
  useSaveSpec,
  useSpecCompat,
  useSpecPresets,
} from "@/api/hooks/series";
import { useShots } from "@/api/hooks/shots";
import type { ImpactAction } from "@/api/schemas/impact";
import type {
  Aspect,
  Delivery,
  OutputSpec,
  Platform,
  SpecPatch,
  SpecPresets,
} from "@/api/schemas/spec";
import { DEMO_SERIES, paths } from "@/app/paths";
import { Chip } from "@/components/Chip";
import { ImpactDialog } from "@/components/ImpactDialog";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioCard, RadioGroup } from "@/components/ui/radio-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatSpecTag, formatTime, formatUsd } from "@/lib/format";
import { modelName as nameOf } from "@/lib/versions";
import { cn } from "@/lib/utils";
import { CompatTable } from "@/pages/spec/CompatTable";
import { SafeAreaPreview } from "@/pages/spec/SafeAreaPreview";

type Draft = Required<SpecPatch>;
const ASPECTS: Aspect[] = ["9:16", "16:9", "3:4", "1:1", "21:9"];
const DELIVERY: Delivery[] = ["1080p", "2k"];
const FPS = [24, 25, 30] as const;
const LENGTHS = ["short", "mid", "long", "xl"] as const;
const SUBTITLES = ["burn", "srt", "both"] as const;

const draftOf = (s: OutputSpec): Draft => ({
  platform: s.platform,
  aspect: s.aspect,
  delivery: s.delivery,
  fps: s.fps,
  episode_len: s.episode_len,
  subtitles: s.subtitles,
  derive: s.derive,
});

const isVertical = (a: Aspect) => a === "9:16" || a === "3:4";
/** Dictionary key of an aspect: i18next reads `:` as a namespace separator. */
const ak = (a: Aspect) => a.replace(":", "x") as "9x16";

function Section({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead?: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <h2 id={id} className="text-base font-bold">
        {title}
      </h2>
      {lead ? <p className="-mt-1.5 text-xs text-muted-foreground">{lead}</p> : null}
      {children}
    </section>
  );
}

/** The aspect's outline at a fixed long edge, for the aspect cards. */
function AspectIcon({ aspect }: { aspect: Aspect }) {
  const [w = 1, h = 1] = aspect.split(":").map(Number);
  const big = 30;
  return (
    <span
      aria-hidden
      className="block rounded-[3px] border-2 border-current"
      style={{
        width: w >= h ? big : Math.round((big * w) / h),
        height: h >= w ? big : Math.round((big * h) / w),
      }}
    />
  );
}

export default function SpecPage() {
  const { t } = useTranslation("spec");
  const { t: tc } = useTranslation();
  const seriesId = useParams().series ?? DEMO_SERIES;
  const spec = useOutputSpec(seriesId);
  const presets = useSpecPresets();
  const episodes = useEpisodes(seriesId);
  const firstEpisode = episodes.data?.[0];
  const shots = useShots(firstEpisode?.id);
  const catalog = useComponentCatalog();
  const save = useSaveSpec(seriesId);
  const preview = useImpactPreview();
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [showSafe, setShowSafe] = useState(true);
  const [showSub, setShowSub] = useState(true);
  if (!draft && spec.data) setDraft(draftOf(spec.data));
  const compat = useSpecCompat(seriesId, draft?.aspect);

  const saved = spec.data;
  const locked = !!saved?.locked_at;
  // A locked spec changes aspect only through the impact preview (SPEC 13.3).
  const pending = !!(draft && saved && locked && draft.aspect !== saved.aspect);

  const setAspect = (aspect: Aspect, platform: Platform, extra: Partial<Draft> = {}) => {
    if (!draft || !saved) return;
    setDraft({ ...draft, ...extra, aspect, platform });
    if (locked && aspect !== saved.aspect)
      preview.mutate(
        { kind: "spec_aspect", target_id: seriesId, patch: { aspect, platform } },
        { onError: (err) => toast.error(errorMessage(tc, err)) },
      );
    else preview.reset();
  };

  const onResolved = (action: ImpactAction) => {
    preview.reset();
    if (action === "undo" && draft && saved)
      setDraft({ ...draft, aspect: saved.aspect, platform: saved.platform });
    else void client.invalidateQueries({ queryKey: seriesKeys.spec(seriesId) });
  };

  const onSave = () => {
    if (!draft || !saved) return;
    if (pending) {
      toast.warning(t("toast.resolveFirst"));
      return;
    }
    const change = Object.fromEntries(
      Object.entries(draft).filter(([k, v]) => saved[k as keyof Draft] !== v),
    ) as SpecPatch;
    if (!Object.keys(change).length) {
      toast.info(t("toast.nothing"));
      return;
    }
    save.mutate(change, {
      onSuccess: (s) =>
        toast.success(
          t("toast.saved", {
            spec: formatSpecTag(s.aspect, s.dims.delivery.w, s.dims.delivery.h, s.fps),
          }),
        ),
      onError: (err) => toast.error(errorMessage(tc, err)),
    });
  };

  const modelName = (key: string) => nameOf(catalog.data?.models ?? [], key);
  const shotCount = shots.data?.length ?? 0;

  return (
    <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-5 px-7 py-6">
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        lead={t("lead")}
        actions={
          <>
            {locked && saved?.locked_at ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    tabIndex={0}
                    className="inline-flex min-h-9 items-center gap-1.5 rounded-md bg-tone-info-bg px-3 text-sm text-tone-info-fg"
                  >
                    <Lock className="size-3.5" aria-hidden />
                    {t("locked", { count: shotCount })}
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {t("lockedTitle", { time: formatTime(saved.locked_at) })}
                </TooltipContent>
              </Tooltip>
            ) : null}
            <Button size="lg" asChild>
              <Link to={paths.step(seriesId, String(firstEpisode?.idx ?? 1), "novel")}>
                {t("next")}
                <ArrowRight aria-hidden />
              </Link>
            </Button>
          </>
        }
      />

      <QueryState query={spec} skeleton={<Skeleton className="h-96 w-full" />}>
        {() =>
          draft && saved && presets.data ? (
            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
              <div className="flex min-w-0 flex-col gap-5">
                <Platforms
                  draft={draft}
                  presets={presets.data}
                  onPick={(id) => {
                    const p = presets.data.platforms.find((x) => x.id === id);
                    if (p?.aspect && p.delivery) setAspect(p.aspect, id, { delivery: p.delivery });
                    else setDraft({ ...draft, platform: id });
                  }}
                />

                <Section id="aspect-title" title={t("aspect.title")}>
                  <div
                    className="grid grid-cols-2 gap-2.5 sm:grid-cols-5"
                    role="group"
                    aria-labelledby="aspect-title"
                  >
                    {ASPECTS.map((a) => {
                      const on = draft.aspect === a;
                      return (
                        <button
                          key={a}
                          type="button"
                          aria-pressed={on}
                          onClick={() => {
                            const keep = presets.data.platforms.find(
                              (p) => p.id === draft.platform,
                            );
                            setAspect(a, keep?.aspect === a ? draft.platform : "custom");
                          }}
                          className={cn(
                            "flex flex-col items-center gap-1.5 rounded-lg border-2 bg-card px-2 py-3 outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            on
                              ? "border-primary bg-accent"
                              : "border-border hover:border-muted-foreground/40",
                          )}
                        >
                          <span className="flex h-9 items-center">
                            <AspectIcon aspect={a} />
                          </span>
                          <span className="text-sm font-bold">{t(`aspect.name.${ak(a)}`)}</span>
                          <span className="text-xs text-muted-foreground">
                            {t(`aspect.tag.${ak(a)}`)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {t(`aspect.note.${ak(draft.aspect)}`)}
                  </p>
                </Section>

                {pending && preview.data ? (
                  <ImpactDialog
                    impact={preview.data}
                    title={t("impact.title", { name: t(`aspect.name.${ak(draft.aspect)}`) })}
                    labels={{
                      mark: t("impact.mark"),
                      rerun: t("impact.rerun", {
                        cost: formatUsd(preview.data.rerun_cost_usd, { cents: true }),
                      }),
                      undo: t("impact.undo", { aspect: saved.aspect }),
                    }}
                    primary="mark"
                    onResolved={onResolved}
                  />
                ) : null}

                <Section id="res-title" title={t("res.title")}>
                  <div className="text-sm font-medium">{t("res.delivery")}</div>
                  <RadioGroup
                    aria-label={t("res.delivery")}
                    value={draft.delivery}
                    onValueChange={(v) => setDraft({ ...draft, delivery: v as Delivery })}
                    className="grid gap-2.5 sm:grid-cols-2"
                  >
                    {DELIVERY.map((d) => {
                      const dims = presets.data.dims[draft.aspect][d];
                      return (
                        <RadioCard
                          key={d}
                          value={d}
                          aria-label={`${t(`res.name.${d}`)} ${dims.w}×${dims.h}`}
                        >
                          <span className="block text-sm">
                            <b>{t(`res.name.${d}`)}</b> {dims.w}×{dims.h}
                          </span>
                          <span className="block text-xs text-muted-foreground">
                            {t(`res.desc.${d}`)}
                          </span>
                        </RadioCard>
                      );
                    })}
                  </RadioGroup>
                  <p className="text-xs text-muted-foreground">
                    {t("res.draft", presets.data.dims[draft.aspect].draft)}
                  </p>
                  <ChipRow
                    label={t("res.fps")}
                    note={t(`res.fpsNote.${draft.fps}`)}
                    options={FPS.map((f) => ({ value: f, label: t(`res.fpsOption.${f}`) }))}
                    value={draft.fps}
                    onChange={(fps) => setDraft({ ...draft, fps })}
                  />
                  <ChipRow
                    label={t("res.len")}
                    note={t(`res.lenNote.${draft.episode_len}`)}
                    options={LENGTHS.map((l) => ({ value: l, label: t(`res.lenOption.${l}`) }))}
                    value={draft.episode_len}
                    onChange={(episode_len) => setDraft({ ...draft, episode_len })}
                  />
                </Section>

                {compat.data ? (
                  <CompatTable
                    rows={compat.data.rows}
                    aspectName={t(`aspect.name.${ak(compat.data.aspect)}`)}
                    modelName={modelName}
                  />
                ) : null}

                <Section id="output-title" title={t("output.title")}>
                  <div className="grid gap-2.5 sm:grid-cols-3">
                    <Tile label={t("output.codec")}>
                      {t(`output.codecValue.${saved.codec}` as "output.codecValue.h264", {
                        defaultValue: saved.codec,
                      })}
                    </Tile>
                    <Tile label={t("output.audio")}>
                      {t("output.audioValue", {
                        khz: saved.audio.sample_rate / 1000,
                        lufs: saved.audio.lufs,
                        peak: saved.audio.peak_dbtp,
                      })}
                    </Tile>
                    <Tile label={t("output.aiMark")}>
                      {t(saved.ai_mark ? "output.aiMarkOn" : "output.aiMarkOff")}
                    </Tile>
                  </div>
                  <ChipRow
                    label={t("output.subs")}
                    options={SUBTITLES.map((s) => ({
                      value: s,
                      label: t(`output.subsOption.${s}`),
                    }))}
                    value={draft.subtitles}
                    onChange={(subtitles) => setDraft({ ...draft, subtitles })}
                  />
                  <Derive draft={draft} onChange={(derive) => setDraft({ ...draft, derive })} />
                </Section>
              </div>

              <aside
                aria-labelledby="preview-title"
                className="flex flex-col gap-3 rounded-xl border bg-card p-4 lg:sticky lg:top-4"
              >
                <h2 id="preview-title" className="text-base font-bold">
                  {t("preview.title")}
                </h2>
                <p className="text-xs leading-relaxed text-muted-foreground">{t("preview.lead")}</p>
                <SafeAreaPreview
                  aspect={draft.aspect}
                  platform={draft.platform}
                  showSafe={showSafe}
                  showSub={showSub}
                  name={t(`aspect.name.${ak(draft.aspect)}`)}
                  caption={t("preview.caption", {
                    name: t(`aspect.name.${ak(draft.aspect)}`),
                    ...presets.data.dims[draft.aspect][draft.delivery],
                    fps: draft.fps,
                  })}
                >
                  <div className="flex w-full flex-col gap-2.5">
                    <label className="flex items-center gap-2.5 text-sm">
                      <Checkbox
                        checked={showSafe}
                        onCheckedChange={(v) => setShowSafe(v === true)}
                      />
                      {t("preview.showSafe")}
                    </label>
                    <label className="flex items-center gap-2.5 text-sm">
                      <Checkbox checked={showSub} onCheckedChange={(v) => setShowSub(v === true)} />
                      {t("preview.showSub")}
                    </label>
                    <Button
                      size="lg"
                      className="mt-1 w-full"
                      disabled={save.isPending}
                      onClick={onSave}
                    >
                      {t("preview.save")}
                    </Button>
                  </div>
                </SafeAreaPreview>
              </aside>
            </div>
          ) : (
            <Skeleton className="h-96 w-full" />
          )
        }
      </QueryState>
    </div>
  );
}

function Platforms({
  draft,
  presets,
  onPick,
}: {
  draft: Draft;
  presets: SpecPresets;
  onPick: (id: Platform) => void;
}) {
  const { t } = useTranslation("spec");
  return (
    <Section id="platform-title" title={t("platform.title")} lead={t("platform.lead")}>
      <div
        className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4"
        role="group"
        aria-labelledby="platform-title"
      >
        {presets.platforms.map((p) => {
          const on = draft.platform === p.id;
          const aspect = p.aspect ?? draft.aspect;
          const dims = presets.dims[aspect][p.delivery ?? draft.delivery];
          return (
            <button
              key={p.id}
              type="button"
              aria-pressed={on}
              onClick={() => onPick(p.id)}
              className={cn(
                "flex flex-col gap-1 rounded-lg border-2 bg-card px-3 py-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring",
                on ? "border-primary" : "border-border hover:border-muted-foreground/40",
              )}
            >
              <span className="text-sm font-bold">{t(`platform.name.${p.id}`)}</span>
              <span className="text-xs text-muted-foreground">{t(`platform.sub.${p.id}`)}</span>
              <span className="font-mono text-xs text-primary">
                {t("platform.spec", { aspect, ...dims })}
              </span>
            </button>
          );
        })}
      </div>
    </Section>
  );
}

function ChipRow<T extends string | number>({
  label,
  note,
  options,
  value,
  onChange,
}: {
  label: string;
  note?: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm font-medium">{label}</div>
      <div role="group" aria-label={label} className="flex flex-wrap gap-2">
        {options.map((o) => (
          <Chip key={o.value} selected={o.value === value} onClick={() => onChange(o.value)}>
            {o.label}
          </Chip>
        ))}
      </div>
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
    </div>
  );
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg bg-muted/60 px-3 py-2.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">{children}</div>
    </div>
  );
}

/** 另出一版: the other orientation at export (outpaint to 16:9, or crop to 9:16). */
function Derive({ draft, onChange }: { draft: Draft; onChange: (d: Aspect | null) => void }) {
  const { t } = useTranslation("spec");
  const vertical = isVertical(draft.aspect);
  const other: Aspect = vertical ? "16:9" : "9:16";
  return (
    <label className="flex items-start gap-2.5">
      <Checkbox
        className="mt-0.5"
        checked={draft.derive !== null}
        onCheckedChange={(v) => onChange(v === true ? other : null)}
      />
      <span className="flex flex-col gap-0.5">
        <span className="text-sm">{t(vertical ? "output.deriveTo169" : "output.deriveTo916")}</span>
        <span className="text-xs text-muted-foreground">
          {t(vertical ? "output.deriveNote169" : "output.deriveNote916")}
        </span>
      </span>
    </label>
  );
}
