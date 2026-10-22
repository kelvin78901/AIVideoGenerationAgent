import { Mic, RotateCw } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { useDubEpisode, useEpisodeDub, useSetLineEmotion } from "@/api/hooks/dub";
import type { Asset } from "@/api/schemas/assets";
import { EMOTIONS, type DubLine, type DubSkip, type DubStart } from "@/api/schemas/dub";
import { AudioPlayer } from "@/components/AudioPlayer";
import { StatusBadge, type Tone } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { formatCost } from "@/lib/format";

const SELECT =
  "h-7 rounded-md border bg-card px-1.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

const STATUS_TONE: Record<DubLine["status"], Tone> = {
  done: "pass",
  stale: "warn",
  missing: "neutral",
  running: "info",
  failed: "fail",
  no_voice: "neutral",
  voice_not_locked: "neutral",
};

/** Lines a 「全部配音」 would dub now (the backend's `TO_DUB`). */
const toDub = (x: DubLine) =>
  x.status === "missing" || x.status === "stale" || x.status === "failed";
const names = (xs: { name: string }[]) => [...new Set(xs.map((x) => x.name))].join("、");

/**
 * 台词配音 n / m · 全部配音, a row of the assets page's progress card (four cells of its grid):
 * the estimate first (句数, cost, which voices hold lines back), then one take per line.
 */
export function DubAllRow({ episodeId, episodeIdx }: { episodeId: string; episodeIdx: number }) {
  const { t } = useTranslation("assets");
  const { t: tc } = useTranslation();
  const dub = useEpisodeDub(episodeId);
  const start = useDubEpisode(episodeId);
  const [plan, setPlan] = useState<DubStart | null>(null);
  if (!dub.data?.total) return null;
  const { done, total, lines } = dub.data;
  const waiting = lines.filter((x) => x.status === "voice_not_locked");
  const any = lines.some(toDub);
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const skipped = (code: DubSkip["code"]) => plan?.skipped.filter((s) => s.code === code) ?? [];

  return (
    <>
      <span className="text-sm font-medium tabular-nums">{t("dub.progress", { done, total })}</span>
      <Progress value={(done / total) * 100} aria-label={t("dub.progress", { done, total })} />
      <span className="text-xs text-muted-foreground">
        {waiting.length
          ? t("dub.waiting", {
              names: names(waiting.map((x) => ({ name: x.voice_name ?? x.speaker }))),
              count: waiting.length,
            })
          : null}
      </span>
      <Button
        variant="outline"
        size="sm"
        className="justify-self-end"
        disabled={!any || start.isPending}
        title={!any && done === total ? t("dub.allDone") : undefined}
        onClick={() => start.mutate({ dry_run: true }, { onSuccess: setPlan, onError })}
      >
        <Mic aria-hidden />
        {t("dub.all")}
      </Button>

      <Dialog open={plan !== null} onOpenChange={(open) => !open && setPlan(null)}>
        {plan ? (
          <DialogContent className="gap-3">
            <DialogTitle>{t("dub.confirmTitle", { n: episodeIdx })}</DialogTitle>
            <DialogDescription asChild>
              <div className="flex flex-col gap-1">
                <span>
                  {plan.lines
                    ? t("dub.confirmLines", {
                        count: plan.lines,
                        cost: formatCost(plan.estimate_usd),
                      })
                    : t("dub.confirmNothing")}
                </span>
                {(
                  [
                    ["voice_not_locked", "dub.skipLocked"],
                    ["no_voice", "dub.skipNoVoice"],
                  ] as const
                ).map(([code, key]) => {
                  const xs = skipped(code);
                  return xs.length ? (
                    <span key={code}>{t(key, { count: xs.length, names: names(xs) })}</span>
                  ) : null;
                })}
                {skipped("product_busy").length ? (
                  <span>{t("dub.skipBusy", { count: skipped("product_busy").length })}</span>
                ) : null}
                <span className="mt-1">{t("dub.confirmHint")}</span>
              </div>
            </DialogDescription>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPlan(null)}>
                {t("dub.cancel")}
              </Button>
              <Button
                disabled={!plan.lines || start.isPending}
                onClick={() =>
                  start.mutate(
                    {},
                    {
                      onSuccess: (out) => {
                        setPlan(null);
                        toast.info(t("dub.started", { count: out.jobs.length }));
                      },
                      onError,
                    },
                  )
                }
              >
                {t("dub.start")}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </>
  );
}

/**
 * A voice's lines in the episode: each one's take (play, length), its emotion (from the tone,
 * or chosen) and 配音 / 重配. Until the voice is locked, nothing can be dubbed.
 */
export function VoiceDubLines({
  asset,
  episodeId,
  episodeIdx,
}: {
  asset: Asset;
  episodeId: string;
  episodeIdx: number;
}) {
  const { t } = useTranslation("assets");
  const dub = useEpisodeDub(episodeId);
  const mine = dub.data?.lines.filter((x) => x.voice_asset_id === asset.id) ?? [];
  const locked = asset.status === "locked";
  return (
    <section aria-label={t("dub.lines", { n: episodeIdx })} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm font-bold">{t("dub.lines", { n: episodeIdx })}</h3>
        <span className="text-xs text-muted-foreground">
          {locked ? t("dub.linesHint") : t("dub.lockFirst", { name: asset.name })}
        </span>
      </div>
      {mine.length ? (
        <ul className="flex flex-col gap-2">
          {mine.map((x) => (
            <DubLineRow key={x.line_id} line={x} episodeId={episodeId} locked={locked} />
          ))}
        </ul>
      ) : dub.data ? (
        <p className="text-xs text-muted-foreground">{t("dub.linesNone")}</p>
      ) : null}
    </section>
  );
}

function DubLineRow({
  line,
  episodeId,
  locked,
}: {
  line: DubLine;
  episodeId: string;
  locked: boolean;
}) {
  const { t } = useTranslation("assets");
  const { t: te } = useTranslation("enums");
  const { t: tc } = useTranslation();
  const start = useDubEpisode(episodeId);
  const setEmotion = useSetLineEmotion(episodeId);
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const emotion = (id: string) => te(`emotion.${id}` as "emotion.calm", { defaultValue: id });
  const running = line.status === "running" || start.isPending;
  return (
    <li className="flex flex-col gap-1.5 rounded-lg border px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span>{line.text}</span>
        {line.tone ? <span className="text-xs text-muted-foreground">{line.tone}</span> : null}
        {line.status !== "done" ? (
          <StatusBadge tone={STATUS_TONE[line.status]} icon={null}>
            {te(`dubStatus.${line.status}`)}
          </StatusBadge>
        ) : null}
        <label className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
          {t("dub.emotion")}
          <select
            className={SELECT}
            aria-label={t("dub.emotion")}
            value={line.emotion_set ? line.emotion : ""}
            disabled={setEmotion.isPending}
            onChange={(e) => {
              const value = e.target.value || null;
              setEmotion.mutate(
                { lineId: line.line_id, emotion: value },
                {
                  onSuccess: (x) => {
                    if (x.audio) toast.info(t("dub.emotionSaved", { emotion: emotion(x.emotion) }));
                  },
                  onError,
                },
              );
            }}
          >
            <option value="">
              {t("dub.emotionAuto", { emotion: emotion(line.tone_emotion) })}
            </option>
            {EMOTIONS.map((id) => (
              <option key={id} value={id}>
                {emotion(id)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex items-center gap-2">
        {line.audio ? (
          <AudioPlayer
            src={fileUrl(line.audio.sha256)}
            waveform={line.audio.waveform}
            duration={line.audio.duration_s}
            label={line.text}
            className="flex-1"
          />
        ) : (
          <span className="flex-1" />
        )}
        <Button
          size="sm"
          variant="outline"
          disabled={!locked || running}
          title={locked ? undefined : t("dub.lockFirst", { name: line.voice_name ?? line.speaker })}
          onClick={() =>
            start.mutate(
              { line_ids: [line.line_id] },
              {
                onSuccess: (out) => {
                  if (out.jobs.length) toast.info(t("dub.redubStarted", { text: line.text }));
                },
                onError,
              },
            )
          }
        >
          {line.audio ? <RotateCw aria-hidden /> : <Mic aria-hidden />}
          {t(line.audio ? "dub.redub" : "dub.dub")}
        </Button>
      </div>
    </li>
  );
}
