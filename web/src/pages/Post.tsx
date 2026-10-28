/** 06 后期 · 时间线与导出 (prototype Post.dc.html). */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useComponentCatalog, useComponentModels } from "@/api/hooks/config";
import { useExportChecks, usePatchClip, useSubtitleText, useTimeline } from "@/api/hooks/post";
import { useProducts } from "@/api/hooks/products";
import { useOutputSpec, useRouteEpisode } from "@/api/hooks/series";
import { useShots } from "@/api/hooks/shots";
import type { ClipPatch } from "@/api/schemas/timeline";
import { paths } from "@/app/paths";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { StepLayout } from "@/components/StepLayout";
import { formatSpecTag } from "@/lib/format";
import { currentVersion, modelName as nameOf } from "@/lib/versions";
import { ClipSettings } from "@/pages/post/ClipSettings";
import { ExportPanel } from "@/pages/post/ExportPanel";
import { Preview } from "@/pages/post/Preview";
import { SubtitlesPanel } from "@/pages/post/SubtitlesPanel";
import { TimelineView } from "@/pages/post/TimelineView";
import { useInspectorStore } from "@/stores/inspector";

const COMPONENTS = ["music", "sfx", "sub"] as const;
/** Playback ticks; the playhead moves in real time. */
const TICK_MS = 250;

export default function PostPage() {
  const { t } = useTranslation("post");
  const { t: tc } = useTranslation();
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const timeline = useTimeline(episode?.id);
  const shots = useShots(episode?.id);
  const spec = useOutputSpec(seriesId);
  const checks = useExportChecks(episode?.id);
  const videos = useProducts({ component: "vid" });
  const episodeProducts = useProducts({ owner: `episode:${episode?.id ?? ""}` });
  const catalog = useComponentCatalog();
  const patchClip = usePatchClip(episode?.id);
  const subtitle = useSubtitleText(episode?.id);
  const component = useInspectorStore((s) => s.component) ?? "music";
  const show = useInspectorStore((s) => s.show);
  const select = useInspectorStore((s) => s.select);
  const models = useComponentModels(component);
  const [clipId, setClipId] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    useInspectorStore.getState().reset();
    useInspectorStore.getState().select("music");
  }, []);

  const data = timeline.data;
  const total = data?.duration_s ?? 0;
  // Opens on the first clip without an adopted take, with the playhead in its middle.
  const firstOpen = data?.clips.find((c) => !c.version_id) ?? data?.clips[0];
  const clip = data?.clips.find((c) => c.id === clipId) ?? firstOpen;
  const head = playhead ?? (firstOpen ? (firstOpen.start_s + firstOpen.end_s) / 2 : 0);

  // Playback: a timer moves the playhead and holds it at the end, which ends playback.
  const end = Math.max(0, total - 0.01);
  const isPlaying = playing && head < end;
  useEffect(() => {
    if (!isPlaying) return;
    const id = setInterval(
      () => setPlayhead((p) => Math.min((p ?? 0) + TICK_MS / 1000, end)),
      TICK_MS,
    );
    return () => clearInterval(id);
  }, [isPlaying, end]);
  const togglePlay = () => {
    if (isPlaying) {
      setPlaying(false);
      return;
    }
    setPlayhead(head >= total - 0.5 ? 0 : head);
    setPlaying(true);
  };

  const byComponent = (id: string) =>
    episodeProducts.data?.find((p) => p.component_id === id && p.owner_type === "episode");
  const product = byComponent(component);
  const payload = (product && currentVersion(product)?.payload) ?? {};
  const num = (k: string) => (typeof payload[k] === "number" ? payload[k] : 0);
  const what = () => {
    if (component === "sfx") return t("what.sfx", { count: num("items") });
    if (component === "sub") return t("what.sub", { count: data?.subtitles.length ?? 0 });
    return t("what.music", { count: num("segments"), seconds: num("seconds") });
  };
  const modelName = (key: string | null | undefined) => nameOf(catalog.data?.models ?? [], key);
  const take = videos.data
    ?.flatMap((p) => p.versions)
    .find((v) => clip?.version_id && v.id === clip.version_id);
  const specTag = spec.data
    ? formatSpecTag(
        spec.data.aspect,
        spec.data.dims.delivery.w,
        spec.data.dims.delivery.h,
        spec.data.fps,
      )
    : "";
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const onPatch = (change: ClipPatch) => {
    if (clip) patchClip.mutate({ id: clip.id, patch: change }, { onError });
  };

  return (
    <StepLayout
      inspector={
        <Inspector components={COMPONENTS.map((id) => ({ id, productId: byComponent(id)?.id }))} />
      }
    >
      <PageHeader step={6} title={t("title")} lead={t("lead")} />

      {product ? (
        <RunBar
          product={product}
          what={what()}
          models={models}
          onEditPrompt={() => show("prompt", component)}
          onOpenHistory={() => show("history", component)}
        />
      ) : null}

      <QueryState query={timeline} skeleton={<Skeleton className="h-96 w-full" />}>
        {(tl) => (
          <>
            <div className="flex flex-wrap items-start gap-5">
              <Preview
                timeline={tl}
                shots={shots.data ?? []}
                aspect={spec.data?.aspect ?? "9:16"}
                playhead={head}
                playing={isPlaying}
                onToggle={togglePlay}
              />
              {clip ? (
                <ClipSettings
                  key={clip.id}
                  clip={clip}
                  take={take}
                  modelName={modelName}
                  generatePath={`${paths.step(seriesId, String(episodeIdx), "generate")}?shot=${encodeURIComponent(clip.shot_id)}`}
                  onPatch={onPatch}
                />
              ) : null}
            </div>
            <TimelineView
              timeline={tl}
              playhead={head}
              selectedClipId={clip?.id}
              onSelectClip={setClipId}
              onPickComponent={(id) => select(id)}
              onNativeAudio={(label) => toast.info(t("timeline.nativeToast", { label }))}
            />
            <div className="flex flex-wrap items-start gap-5">
              <SubtitlesPanel
                subtitles={tl.subtitles}
                onDraft={subtitle.draft}
                onSave={(id, text) => subtitle.save.mutate({ id, text }, { onError })}
              />
              <ExportPanel
                episodeId={episode?.id}
                checks={checks.data?.checks ?? []}
                specTag={specTag}
              />
            </div>
          </>
        )}
      </QueryState>
    </StepLayout>
  );
}
