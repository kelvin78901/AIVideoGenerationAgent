/**
 * Editing the plan (分集规划): one beat (text, emotion, the episode it belongs to) or one episode
 * (集名、钩子、卡点、预计时长). Saving sends only what changed; each save is an adopted `edit`
 * version of 分集规划 on the backend.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { usePatchBeat, useUpdateEpisode } from "@/api/hooks/series";
import type { Beat, BeatPatch, Episode, EpisodePatch } from "@/api/schemas/episodes";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/form";
import { Slider } from "@/components/ui/slider";
import { formatEmotion } from "@/lib/beats";

const SELECT =
  "h-9 rounded-md border border-input bg-card px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40";

export function BeatDialog({
  seriesId,
  episodes,
  beat,
  onClose,
}: {
  seriesId: string;
  episodes: Episode[];
  /** The beat being edited; null = closed. */
  beat: Beat | null;
  onClose: () => void;
}) {
  return beat ? (
    <BeatForm key={beat.id} seriesId={seriesId} episodes={episodes} beat={beat} onClose={onClose} />
  ) : null;
}

function BeatForm({
  seriesId,
  episodes,
  beat,
  onClose,
}: {
  seriesId: string;
  episodes: Episode[];
  beat: Beat;
  onClose: () => void;
}) {
  const { t } = useTranslation("script");
  const { t: tc } = useTranslation();
  const save = usePatchBeat(seriesId);
  const [text, setText] = useState(beat.text);
  const [emotion, setEmotion] = useState(beat.emotion);
  const [episodeId, setEpisodeId] = useState(beat.episode_id);

  const submit = () => {
    const body: BeatPatch = {};
    if (text.trim() !== beat.text) body.text = text.trim();
    if (emotion !== beat.emotion) body.emotion = emotion;
    if (episodeId !== beat.episode_id) body.episode_id = episodeId;
    if (Object.keys(body).length === 0) return onClose();
    const target = episodes.find((e) => e.id === episodeId);
    save.mutate(
      { id: beat.id, ...body },
      {
        onSuccess: () => {
          toast.success(
            body.episode_id && target
              ? t("board.moved", { n: target.idx, idx: target.beats.length + 1 })
              : t("board.saved"),
          );
          onClose();
        },
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );
  };

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent className="max-w-lg gap-3.5" closeLabel={t("board.beatDialog.cancel")}>
        <DialogTitle>{t("board.beatDialog.title")}</DialogTitle>
        <DialogDescription>{t("board.beatDialog.lead")}</DialogDescription>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="beat-text">{t("board.beatDialog.text")}</Label>
          <Textarea
            id="beat-text"
            rows={2}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium">
            {t("board.beatDialog.emotion", { value: formatEmotion(emotion) })}
          </span>
          <div className="flex items-center gap-3 text-xs whitespace-nowrap text-muted-foreground">
            <span>{t("board.beatDialog.low")}</span>
            <Slider
              min={-1}
              max={1}
              step={0.05}
              value={[emotion]}
              onValueChange={([v]) => setEmotion(Math.round((v ?? 0) * 100) / 100)}
              thumbLabel={t("board.beatDialog.emotionLabel")}
            />
            <span>{t("board.beatDialog.high")}</span>
          </div>
        </div>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          {t("board.beatDialog.episode")}
          <select
            value={episodeId}
            onChange={(e) => setEpisodeId(e.target.value)}
            className={SELECT}
          >
            {episodes.map((e) => (
              <option key={e.id} value={e.id}>
                {t("episodes.name", { n: e.idx, title: e.title })}
              </option>
            ))}
          </select>
        </label>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("board.beatDialog.cancel")}
          </Button>
          <Button onClick={submit} disabled={save.isPending || !text.trim()}>
            {t("board.beatDialog.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EpisodeDialog({
  episode,
  onClose,
}: {
  /** The episode being edited; null = closed. */
  episode: Episode | null;
  onClose: () => void;
}) {
  return episode ? <EpisodeForm key={episode.id} episode={episode} onClose={onClose} /> : null;
}

function EpisodeForm({ episode, onClose }: { episode: Episode; onClose: () => void }) {
  const { t } = useTranslation("script");
  const { t: tc } = useTranslation();
  const save = useUpdateEpisode(episode.id);
  const [title, setTitle] = useState(episode.title);
  const [hook, setHook] = useState(episode.hook ?? "");
  const [cliffhanger, setCliffhanger] = useState(episode.cliffhanger ?? "");
  const [seconds, setSeconds] = useState(episode.target_seconds?.toString() ?? "");

  const submit = () => {
    const body: EpisodePatch = {};
    if (title.trim() !== episode.title) body.title = title.trim();
    if (hook.trim() !== (episode.hook ?? "")) body.hook = hook.trim();
    if (cliffhanger.trim() !== (episode.cliffhanger ?? "")) body.cliffhanger = cliffhanger.trim();
    const s = Number(seconds);
    if (seconds && Number.isInteger(s) && s > 0 && s !== episode.target_seconds)
      body.target_seconds = s;
    if (Object.keys(body).length === 0) return onClose();
    save.mutate(body, {
      onSuccess: () => {
        toast.success(t("board.saved"));
        onClose();
      },
      onError: (err) => toast.error(errorMessage(tc, err)),
    });
  };

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent className="max-w-lg gap-3.5" closeLabel={t("board.episodeDialog.cancel")}>
        <DialogTitle>{t("board.episodeDialog.title", { n: episode.idx })}</DialogTitle>
        <DialogDescription>{t("board.episodeDialog.lead")}</DialogDescription>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="episode-title">{t("board.episodeDialog.name")}</Label>
          <Input id="episode-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="episode-hook">{t("board.episodeDialog.hook")}</Label>
          <Textarea
            id="episode-hook"
            rows={2}
            value={hook}
            onChange={(e) => setHook(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="episode-cliffhanger">{t("board.episodeDialog.cliffhanger")}</Label>
          <Textarea
            id="episode-cliffhanger"
            rows={2}
            value={cliffhanger}
            onChange={(e) => setCliffhanger(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="episode-seconds">{t("board.episodeDialog.seconds")}</Label>
          <Input
            id="episode-seconds"
            type="number"
            min={1}
            className="w-32"
            value={seconds}
            onChange={(e) => setSeconds(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("board.episodeDialog.cancel")}
          </Button>
          <Button onClick={submit} disabled={save.isPending || !title.trim()}>
            {t("board.episodeDialog.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
