/** 04 分镜 · 关键帧与镜头设定 (prototype Storyboard.dc.html). */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useAssets } from "@/api/hooks/assets";
import { useComponentModels } from "@/api/hooks/config";
import { useProduct, useProducts } from "@/api/hooks/products";
import { useScript } from "@/api/hooks/script";
import { useOutputSpec, useRouteEpisode } from "@/api/hooks/series";
import { usePatchShot, useShots } from "@/api/hooks/shots";
import type { ShotPatch } from "@/api/schemas/shots";
import { paths } from "@/app/paths";
import { GateButton } from "@/components/GateButton";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { StepLayout } from "@/components/StepLayout";
import { scriptBlocks, useBlockLead } from "@/pages/script/blocks";
import { PreviewStrip } from "@/pages/storyboard/PreviewStrip";
import { ShotCards } from "@/pages/storyboard/ShotCards";
import { ShotSettings } from "@/pages/storyboard/ShotSettings";
import { useInspectorStore } from "@/stores/inspector";

export default function StoryboardPage() {
  const { t } = useTranslation("storyboard");
  const { t: tc } = useTranslation();
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const shots = useShots(episode?.id);
  const spec = useOutputSpec(seriesId);
  const assets = useAssets(seriesId);
  const episodeProducts = useProducts({ owner: `episode:${episode?.id ?? ""}` });
  const patchShot = usePatchShot(episode?.id);
  const component = useInspectorStore((s) => s.component) ?? "kf";
  const show = useInspectorStore((s) => s.show);
  const models = useComponentModels(component);
  const script = useScript(episode?.id);
  const leadOf = useBlockLead();
  // A script line's 「镜头 1-04」 links here with `?shot=`; a shot the user picks wins until the
  // link changes.
  const [search] = useSearchParams();
  const linked = search.get("shot");
  const [picked, setPicked] = useState<{ id: string; link: string | null } | null>(null);
  const selectedId = picked && picked.link === linked ? picked.id : linked;
  const setSelectedId = (id: string) => setPicked({ id, link: linked });

  useEffect(() => {
    useInspectorStore.getState().reset();
    useInspectorStore.getState().select("kf");
  }, []);

  const list = shots.data ?? [];
  const shot =
    list.find((s) => s.id === selectedId) ?? list.find((s) => s.label === "1-04") ?? list[0];
  const plan = episodeProducts.data?.find((p) => p.component_id === "plan");
  const keyframe = useProduct(shot?.keyframe_product_id ?? undefined);
  const product = component === "plan" ? plan : keyframe.data;
  const aspect = spec.data?.aspect ?? "9:16";
  const seconds = list.reduce((n, s) => n + s.duration_s, 0);
  const ep = String(episodeIdx);
  const lines = (script.data ? scriptBlocks(script.data) : [])
    .filter((b) => b.kind !== "scene" && shot?.line_ids.includes(b.id))
    .map((b) => ({ id: b.id, lead: leadOf(b), text: b.text, paras: b.paras }));

  const onPatch = (change: ShotPatch) => {
    if (!shot) return;
    patchShot.mutate(
      { id: shot.id, patch: change },
      {
        onSuccess: (s) => {
          if (change.confirmed !== undefined)
            toast.success(
              t(change.confirmed ? "shot.confirmed" : "shot.unconfirmed", { id: s.label }),
            );
        },
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );
  };

  return (
    <StepLayout
      inspector={
        <Inspector
          components={[
            { id: "plan", productId: plan?.id },
            { id: "kf", productId: shot?.keyframe_product_id ?? undefined },
          ]}
          item={shot ? `shot:${shot.label}` : null}
        />
      }
    >
      <PageHeader
        step={4}
        title={t("title")}
        lead={t("lead")}
        actions={
          <GateButton
            gate="storyboard"
            scopeId={episode?.id}
            label={t("gate")}
            to={paths.step(seriesId, ep, "generate")}
          />
        }
      >
        {spec.data ? (
          <Link
            to={paths.spec(seriesId)}
            className="mt-2 inline-block text-xs text-primary underline-offset-4 hover:underline"
          >
            {t("spec", {
              aspect: spec.data.aspect,
              w: spec.data.dims.delivery.w,
              h: spec.data.dims.delivery.h,
            })}
          </Link>
        ) : null}
      </PageHeader>

      <QueryState query={shots} skeleton={<Skeleton className="h-96 w-full" />}>
        {() =>
          shot ? (
            <>
              <PreviewStrip
                shots={list}
                aspect={aspect}
                selectedId={shot.id}
                onSelect={setSelectedId}
              />
              {product ? (
                <RunBar
                  product={product}
                  what={
                    component === "plan"
                      ? t("what.plan", { n: episodeIdx, count: list.length, seconds })
                      : t("what.kf", { id: shot.label })
                  }
                  models={models}
                  onEditPrompt={() => show("prompt", component)}
                  onOpenHistory={() => show("history", component)}
                />
              ) : null}
              <ShotCards
                shots={list}
                aspect={aspect}
                selectedId={shot.id}
                onSelect={setSelectedId}
              />
              <ShotSettings
                key={shot.id}
                shot={shot}
                assets={assets.data ?? []}
                aspect={aspect}
                assetsPath={paths.step(seriesId, ep, "assets")}
                lines={lines}
                scriptPath={(id) =>
                  `${paths.step(seriesId, ep, "script")}?line=${encodeURIComponent(id)}`
                }
                novelPath={(idx) => `${paths.step(seriesId, ep, "novel")}?para=${idx}`}
                busy={patchShot.isPending}
                onPatch={onPatch}
              />
            </>
          ) : null
        }
      </QueryState>
    </StepLayout>
  );
}
