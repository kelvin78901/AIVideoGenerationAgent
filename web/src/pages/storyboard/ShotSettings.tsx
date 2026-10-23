import { CheckCircle2, Combine, Film, Plus, RotateCcw, Scissors } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { fileUrl } from "@/api/client";
import { useProduct } from "@/api/hooks/products";
import { CandidatesPayloadSchema, type Asset } from "@/api/schemas/assets";
import {
  AudioModeSchema,
  CameraMoveSchema,
  FramingSchema,
  ShotTypeSchema,
  type Shot,
  type ShotPatch,
} from "@/api/schemas/shots";
import type { Aspect } from "@/api/schemas/spec";
import { CandidateGrid } from "@/components/CandidateGrid";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { FinalButton } from "@/components/FinalButton";
import { MediaThumb } from "@/components/MediaThumb";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/form";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { currentVersion } from "@/lib/versions";
import { Blocking } from "@/pages/storyboard/Blocking";
import { durationSource } from "@/pages/storyboard/duration";

const LETTERS = "ABC";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-sm font-medium">{label}</div>
      {children}
    </div>
  );
}

/** 首帧: the shot's own keyframe candidates (pick one; a local draft can be finished on the API
 * model, M3 混合), or the last frame of an earlier shot. */
function FirstFrame({
  shot,
  aspect,
  onPick,
}: {
  shot: Shot;
  aspect: Aspect;
  onPick: (i: number) => void;
}) {
  const { t } = useTranslation("storyboard");
  const product = useProduct(shot.keyframe_product_id ?? undefined);
  const version = product.data ? currentVersion(product.data) : undefined;
  const parsed = CandidatesPayloadSchema.safeParse(version?.payload);
  const cands = parsed.success ? parsed.data.candidates : [];

  if (shot.shot_type === "continuous") {
    const from = shot.tail_from ?? "";
    return (
      <div className="flex items-start gap-3 rounded-md border border-dashed p-3">
        <div className="w-16 shrink-0">
          <MediaThumb aspect={aspect} seed={from} label={from} dashed />
        </div>
        <div className="flex flex-col gap-1 text-sm">
          <div className="font-medium">{t("shot.tailTitle", { id: from })}</div>
          <p className="text-muted-foreground">{t("shot.tailText", { id: from })}</p>
          <p className="text-xs text-muted-foreground">{shot.tail_note ?? t("shot.tailDefault")}</p>
        </div>
      </div>
    );
  }
  if (!version || !cands.length || !product.data)
    return <EmptyState icon={Film} title={t("shot.noKeyframe")} />;
  const made = t(version.stage === "final" ? "shot.kfFinal" : "shot.kfDraft");
  const cards = cands.map((c, i) => {
    const file = version.files.find((f) => f.role === "candidate" && f.idx === i);
    return {
      label: t("shot.kfLabel", { n: version.n, letter: LETTERS[i] }),
      letter: LETTERS[i] ?? "",
      seed: `${shot.id}-${version.n}-${i}`,
      src: file ? fileUrl(file.sha256) : null,
      meta: <span className="text-xs text-muted-foreground">{c.label ?? made}</span>,
    };
  });
  return (
    <div className="flex flex-col gap-2">
      <CandidateGrid
        label={t("shot.firstFrame")}
        cards={cards}
        aspect={aspect}
        picked={shot.keyframe_pick}
        pickedText={t("shot.picked")}
        disabled={shot.confirmed}
        onPick={onPick}
      />
      {shot.confirmed ? null : (
        <div>
          <FinalButton
            componentId="kf"
            product={product.data}
            version={version}
            pick={shot.keyframe_pick}
            letter={LETTERS[shot.keyframe_pick] ?? "A"}
          />
        </div>
      )}
    </div>
  );
}

/** A script line the shot films, as the script page shows it (镜头 → 剧本行 → 原文). */
export interface ShotLine {
  id: string;
  /** 「△ 」 / 「林晚（低声，愣住）：」 */
  lead: string;
  text: string;
  paras: number[];
}

/** 时长: how long the shot runs and where that comes from (its audio, the user, the plan);
 * typed in, saved on leaving it; 「恢复」 goes back to automatic. */
function DurationNote({ shot, onPatch }: { shot: Shot; onPatch: (patch: ShotPatch) => void }) {
  const { t } = useTranslation("storyboard");
  const source = durationSource(shot);
  const text =
    source === "audio"
      ? t("shot.durationSource.audio", { min: shot.min_s })
      : source === "manual" && shot.min_s > 0
        ? t("shot.durationSource.manualMin", { min: shot.min_s })
        : t(`shot.durationSource.${source}`);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span>{text}</span>
      {shot.manual_s !== null ? (
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-xs"
          onClick={() => onPatch({ duration_s: null })}
        >
          <RotateCcw aria-hidden />
          {shot.min_s > 0 || shot.planned_s === null
            ? t("shot.durationReset")
            : t("shot.durationResetPlan", { s: shot.planned_s })}
        </Button>
      ) : null}
      {shot.split_hint && shot.longest_s !== null ? (
        <span role="status" className="text-tone-warn-fg">
          {t("shot.splitHint", { max: shot.longest_s })}
        </span>
      ) : null}
    </div>
  );
}

/** 拆分 (several lines: choose where to cut) and 和下一个合并 (the next shot of the scene). */
function SplitMerge({
  lines,
  canMerge,
  busy,
  onSplit,
  onMerge,
}: {
  lines: ShotLine[];
  canMerge: boolean;
  busy: boolean;
  onSplit: (afterLineId?: string) => void;
  onMerge: () => void;
}) {
  const { t } = useTranslation("storyboard");
  const [open, setOpen] = useState(false);
  const split = (
    <Button
      size="sm"
      variant="outline"
      disabled={busy}
      onClick={lines.length > 1 ? undefined : () => onSplit()}
    >
      <Scissors aria-hidden />
      {t("shot.split")}
    </Button>
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      {lines.length > 1 ? (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>{split}</PopoverTrigger>
          <PopoverContent className="flex w-80 flex-col gap-1 p-2">
            {lines.slice(0, -1).map((l) => (
              <Button
                key={l.id}
                size="sm"
                variant="ghost"
                className="h-auto justify-start py-1.5 text-left whitespace-normal"
                onClick={() => {
                  setOpen(false);
                  onSplit(l.id);
                }}
              >
                {t("shot.splitAfter", { text: l.text })}
              </Button>
            ))}
          </PopoverContent>
        </Popover>
      ) : (
        split
      )}
      <Button
        size="sm"
        variant="outline"
        disabled={busy || !canMerge}
        title={canMerge ? undefined : t("shot.mergeNone")}
        onClick={onMerge}
      >
        <Combine aria-hidden />
        {t("shot.merge")}
      </Button>
    </div>
  );
}

/** 镜头设定: everything about one shot, saved as you change it. */
export function ShotSettings({
  shot,
  assets,
  aspect,
  assetsPath,
  lines,
  scriptPath,
  novelPath,
  busy,
  canMerge,
  onPatch,
  onSplit,
  onMerge,
}: {
  shot: Shot;
  assets: Asset[];
  aspect: Aspect;
  assetsPath: string;
  lines: ShotLine[];
  /** The script page with this line selected. */
  scriptPath: (lineId: string) => string;
  /** The novel page with this paragraph (0-based) in view. */
  novelPath: (idx: number) => string;
  busy: boolean;
  /** The next shot is in the same scene. */
  canMerge: boolean;
  onPatch: (patch: ShotPatch) => void;
  onSplit: (afterLineId?: string) => void;
  onMerge: () => void;
}) {
  const { t } = useTranslation("storyboard");
  const { t: te } = useTranslation("enums");
  const ids = useId();
  const [duration, setDuration] = useState(String(shot.duration_s));
  const [intent, setIntent] = useState(shot.intent);
  const refs = shot.asset_ids.flatMap((id) => assets.find((a) => a.id === id) ?? []);
  const addable = assets.filter((a) => a.status === "locked" && !shot.asset_ids.includes(a.id));
  const textAsset = refs.find((a) => a.text);

  return (
    <section
      aria-label={t("shot.label")}
      className="flex flex-col gap-4 rounded-lg border bg-card p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-bold">{t("shot.title", { id: shot.label })}</h2>
        <span className="text-xs text-muted-foreground">
          {t("shot.scene", { n: shot.scene_no, place: shot.scene_place })}
        </span>
        <StatusBadge tone={shot.confirmed && !shot.confirm_stale ? "info" : "warn"} icon={null}>
          {t(
            shot.confirm_stale
              ? "status.stale"
              : shot.confirmed
                ? "status.confirmed"
                : "status.draft",
          )}
        </StatusBadge>
        <Button
          className="ml-auto"
          variant={shot.confirmed ? "outline" : "default"}
          disabled={busy}
          onClick={() => onPatch({ confirmed: !shot.confirmed })}
        >
          <CheckCircle2 aria-hidden />
          {t(shot.confirmed ? "shot.unconfirm" : "shot.confirm")}
        </Button>
      </div>

      <Field label={t("shot.lines")}>
        {lines.length ? (
          <ul className="flex flex-col gap-1 text-sm">
            {lines.map((l) => (
              <li key={l.id} className="flex flex-wrap items-baseline gap-x-2">
                <Link
                  to={scriptPath(l.id)}
                  aria-label={t("shot.lineLink", { text: l.text })}
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {l.lead}
                  {l.text}
                </Link>
                {l.paras.length ? (
                  <Link
                    to={novelPath(l.paras[0] ?? 0)}
                    className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                  >
                    {t("shot.paras", { paras: l.paras.map((p) => p + 1).join(t("shot.paraSep")) })}
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("shot.noLines")}</p>
        )}
        <SplitMerge
          lines={lines}
          canMerge={canMerge}
          busy={busy}
          onSplit={onSplit}
          onMerge={onMerge}
        />
      </Field>

      <div className="flex flex-col gap-2">
        <div className="flex items-baseline gap-2">
          <h3 className="text-sm font-bold">{t("shot.firstFrame")}</h3>
          <span className="text-xs text-muted-foreground">
            {shot.shot_type === "continuous"
              ? t("shot.tailOf", { id: shot.tail_from ?? "" })
              : t("shot.ownKeyframe")}
          </span>
        </div>
        <FirstFrame shot={shot} aspect={aspect} onPick={(i) => onPatch({ keyframe_pick: i })} />
      </div>

      <Field label={t("shot.type")}>
        <SegmentedControl
          label={t("shot.type")}
          value={shot.shot_type}
          onChange={(shot_type) => onPatch({ shot_type })}
          options={ShotTypeSchema.options.map((v) => ({ value: v, label: te(`shotType.${v}`) }))}
        />
        <p className="text-xs text-muted-foreground">{t(`shot.typeHint.${shot.shot_type}`)}</p>
      </Field>

      <div className="grid gap-4 md:grid-cols-[1fr_1fr_8rem]">
        <Field label={t("shot.framing")}>
          <div role="radiogroup" aria-label={t("shot.framing")} className="flex flex-wrap gap-1.5">
            {FramingSchema.options.map((f) => (
              <Chip
                key={f}
                role="radio"
                selected={shot.framing === f}
                onClick={() => onPatch({ framing: f })}
              >
                {te(`framing.${f}`)}
              </Chip>
            ))}
          </div>
        </Field>
        <Field label={t("shot.move")}>
          <div role="radiogroup" aria-label={t("shot.move")} className="flex flex-wrap gap-1.5">
            {CameraMoveSchema.options.map((m) => (
              <Chip
                key={m}
                role="radio"
                selected={shot.camera_move === m}
                onClick={() => onPatch({ camera_move: m })}
              >
                {te(`cameraMove.${m}`)}
              </Chip>
            ))}
          </div>
        </Field>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${ids}-dur`}>{t("shot.duration")}</Label>
          <Input
            id={`${ids}-dur`}
            type="number"
            min={shot.min_s || 0.5}
            max={60}
            step={0.5}
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            onBlur={() => {
              const n = Number(duration);
              if (Number.isFinite(n) && n > 0 && n <= 60 && n !== shot.duration_s)
                onPatch({ duration_s: n });
              else setDuration(String(shot.duration_s));
            }}
          />
        </div>
      </div>
      <DurationNote shot={shot} onPatch={onPatch} />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${ids}-desc`}>{t("shot.desc")}</Label>
        <Textarea
          id={`${ids}-desc`}
          rows={3}
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          onBlur={() => {
            if (intent !== shot.intent) onPatch({ intent });
          }}
        />
      </div>

      <Field label={t("shot.refs")}>
        <div className="flex flex-wrap items-center gap-1.5">
          {refs.map((a) => {
            const ok = a.status === "locked";
            return (
              <Link
                key={a.id}
                to={assetsPath}
                className={cn(
                  "rounded-md border px-2 py-1 text-xs",
                  ok
                    ? "border-tone-info-border bg-tone-info-bg text-tone-info-fg"
                    : "border-tone-warn-border bg-tone-warn-bg text-tone-warn-fg",
                )}
              >
                {te(`assetKind.${a.kind}`)} · {a.name}
                {ok ? "" : ` · ${t("shot.unlocked")}`}
              </Link>
            );
          })}
          <Popover>
            <PopoverTrigger asChild>
              <Button size="sm" variant="outline">
                <Plus aria-hidden />
                {t("shot.addRef")}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="flex w-64 flex-col gap-1 p-2">
              {addable.length ? (
                addable.map((a) => (
                  <Button
                    key={a.id}
                    size="sm"
                    variant="ghost"
                    className="justify-start"
                    onClick={() => onPatch({ asset_ids: [...shot.asset_ids, a.id] })}
                  >
                    {te(`assetKind.${a.kind}`)} · {a.name}
                  </Button>
                ))
              ) : (
                <span className="p-1 text-xs text-muted-foreground">{t("shot.noMoreRefs")}</span>
              )}
            </PopoverContent>
          </Popover>
        </div>
      </Field>

      <Field label={t("shot.sound")}>
        <div className="text-sm">
          {shot.dialogue ?? t("shot.noDialogue")}
          {shot.sound ? ` · ${t("shot.ambience", { sound: shot.sound })}` : ""}
        </div>
        <SegmentedControl
          size="sm"
          label={t("shot.audio")}
          value={shot.audio_mode}
          onChange={(audio_mode) => onPatch({ audio_mode })}
          options={AudioModeSchema.options.map((v) => ({ value: v, label: te(`audioMode.${v}`) }))}
        />
        <p className="text-xs text-muted-foreground">{t(`shot.audioHint.${shot.audio_mode}`)}</p>
      </Field>

      <Field label={t("shot.blocking")}>
        <div className="max-w-md">
          <Blocking
            items={shot.blocking}
            framing={shot.framing}
            onChange={(blocking) => onPatch({ blocking })}
          />
        </div>
        <p className="text-xs text-muted-foreground">{t("shot.blockingHint")}</p>
      </Field>

      {textAsset?.text ? (
        <div className="text-sm">
          {t("shot.text", { text: textAsset.text.exact })} ·{" "}
          <Link to={assetsPath} className="text-primary underline-offset-4 hover:underline">
            {t("shot.textLink")}
          </Link>
        </div>
      ) : null}
    </section>
  );
}
