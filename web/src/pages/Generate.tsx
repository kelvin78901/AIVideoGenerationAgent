/** 05 生成 · 候选墙与自动质检 (prototype Generate.dc.html). */
import { Layers } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useAssets } from "@/api/hooks/assets";
import { useComponentCatalog, useComponentModels, useResolvedConfig } from "@/api/hooks/config";
import { useGenerateLog, useGenerateRules } from "@/api/hooks/generate";
import { useProduct, useProducts } from "@/api/hooks/products";
import {
  useMachineProfile,
  useMetricsSummary,
  useOutputSpec,
  useRouteEpisode,
} from "@/api/hooks/series";
import { useShots } from "@/api/hooks/shots";
import { useJobs } from "@/api/hooks/useJobs";
import type { Product } from "@/api/schemas/products";
import type { Shot } from "@/api/schemas/shots";
import { paths } from "@/app/paths";
import { GateButton } from "@/components/GateButton";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { StepLayout } from "@/components/StepLayout";
import { Button } from "@/components/ui/button";
import { takeStatus } from "@/lib/takes";
import { modelName as nameOf } from "@/lib/versions";
import { RulesPanel } from "@/pages/generate/RulesPanel";
import { RunLog } from "@/pages/generate/RunLog";
import { ShotPills } from "@/pages/generate/ShotPills";
import { StatusCards } from "@/pages/generate/StatusCards";
import { TakeWall, type UpscaleRoute } from "@/pages/generate/TakeWall";
import { primaryModelKey } from "@/lib/config";
import { useInspectorStore } from "@/stores/inspector";

export default function GeneratePage() {
  const { t } = useTranslation("generate");
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const shots = useShots(episode?.id);
  const spec = useOutputSpec(seriesId);
  const assets = useAssets(seriesId);
  const videos = useProducts({ component: "vid" });
  const episodeProducts = useProducts({ owner: `episode:${episode?.id ?? ""}` });
  const catalog = useComponentCatalog();
  const jobs = useJobs();
  const profile = useMachineProfile();
  const summary = useMetricsSummary("episode", episode?.id);
  const rules = useGenerateRules(seriesId);
  const log = useGenerateLog(episode?.id);
  const upConfig = useResolvedConfig("up");
  const component = useInspectorStore((s) => s.component) ?? "vid";
  const show = useInspectorStore((s) => s.show);
  const models = useComponentModels(component);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    useInspectorStore.getState().reset();
    useInspectorStore.getState().select("vid");
  }, []);

  const list = shots.data ?? [];
  const videoOf = (s: Shot | undefined): Product | undefined =>
    s ? videos.data?.find((p) => p.id === s.video_product_id) : undefined;
  const byLabel = (label: string) => videoOf(list.find((s) => s.label === label));
  const statusOf = (s: Shot) => takeStatus(s, videoOf(s), byLabel);
  // Opens on the first shot with takes to pick, and stays there after adopting.
  const firstPick = list.find((s) => statusOf(s) === "picking") ?? list[0];
  if (selectedId === null && videos.data && firstPick) setSelectedId(firstPick.id);
  const shot = list.find((s) => s.id === selectedId) ?? firstPick;
  const video = useProduct(shot?.video_product_id ?? undefined);
  const videoProduct = video.data ?? videoOf(shot);
  const episodeList = episodeProducts.data ?? [];
  const byComponent = (id: string) => episodeList.find((p) => p.component_id === id);
  const product = component === "vid" ? videoProduct : byComponent(component);
  const aspect = spec.data?.aspect ?? "9:16";
  const ep = String(episodeIdx);
  const modelName = (key: string | null | undefined) => nameOf(catalog.data?.models ?? [], key);

  const episodeVideos = list.map(videoOf).filter((p): p is Product => !!p);
  const adoptedCount = episodeVideos.filter((p) => p.adopted_version_id).length;
  const lipCount = episodeVideos.filter((p) =>
    p.versions
      .find((v) => v.id === p.adopted_version_id)
      ?.qa?.checks.some((c) => c.metric === "lipsync" && c.ok === false),
  ).length;
  const queued = list.filter((s) => statusOf(s) === "queued");
  const textInPost = (s: Shot) =>
    (assets.data ?? []).some((a) => s.asset_ids.includes(a.id) && a.text?.method === "composite");

  const upKey = upConfig.data ? primaryModelKey(upConfig.data.values) : undefined;
  const upModel = catalog.data?.models.find((m) => m.key === upKey);
  const upscale: UpscaleRoute | undefined =
    upModel && shot
      ? {
          model: upModel.key,
          where: upModel.where,
          costUsd:
            upModel.price && upModel.price.unit === "second"
              ? Math.round(upModel.price.amount * shot.duration_s * 100) / 100
              : 0,
        }
      : undefined;

  const what = () => {
    if (component === "up") return t("what.up", { count: adoptedCount });
    if (component === "lip") return t("what.lip", { count: lipCount });
    if (component === "qa") return t("what.qa");
    return t("what.vid", { id: shot?.label ?? "" });
  };

  return (
    <StepLayout
      inspector={
        <Inspector
          components={[
            { id: "vid", productId: shot?.video_product_id ?? undefined },
            { id: "up", productId: byComponent("up")?.id },
            { id: "lip", productId: byComponent("lip")?.id },
            { id: "qa", productId: byComponent("qa")?.id },
          ]}
          item={shot && component === "vid" ? `shot:${shot.label}` : null}
        />
      }
    >
      <PageHeader
        step={5}
        title={t("title")}
        lead={t("lead")}
        actions={
          <>
            <Button variant="outline" size="lg" asChild>
              <Link to={paths.sync(seriesId)}>
                <Layers aria-hidden />
                {t("comfy")}
              </Link>
            </Button>
            <GateButton
              gate="takes"
              episodeId={episode?.id}
              label={t("gate")}
              to={paths.step(seriesId, ep, "post")}
            />
          </>
        }
      />

      <QueryState query={shots} skeleton={<Skeleton className="h-96 w-full" />}>
        {() =>
          shot ? (
            <>
              <StatusCards
                jobs={jobs.data}
                profile={profile.data}
                shots={list}
                products={episodeVideos}
                spentUsd={summary.data?.spent_usd}
                shotCapUsd={rules.data?.shot_cap_usd}
                modelName={modelName}
                dashboardPath={paths.dashboard(seriesId)}
              />
              <ShotPills
                shots={list}
                statusOf={statusOf}
                selectedId={shot.id}
                onSelect={(id) => {
                  setSelectedId(id);
                  useInspectorStore.getState().select("vid");
                }}
              />
              {product ? (
                <RunBar
                  product={product}
                  what={what()}
                  models={models}
                  variant={component === "vid" ? "take" : "default"}
                  onEditPrompt={() => show("prompt", component)}
                  onOpenHistory={() => show("history", component)}
                />
              ) : null}
              <TakeWall
                key={shot.id}
                shot={shot}
                shots={list}
                status={statusOf(shot)}
                product={videoProduct}
                aspect={aspect}
                queuePos={queued.findIndex((s) => s.id === shot.id) + 1}
                textInPost={textInPost(shot)}
                modelName={modelName}
                upscale={upscale}
                episodeId={episode?.id}
              />
              <div className="flex flex-wrap items-start gap-5">
                {rules.data ? <RulesPanel seriesId={seriesId} rules={rules.data} /> : null}
                <RunLog entries={log.data ?? []} modelName={modelName} />
              </div>
            </>
          ) : null
        }
      </QueryState>
    </StepLayout>
  );
}
