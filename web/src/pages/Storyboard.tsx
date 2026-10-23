/** 04 分镜 · 关键帧与镜头设定 (prototype Storyboard.dc.html). A confirmed shot (or a shot of a
 * confirmed storyboard) is changed through the impact preview (`shot_edit`): its confirmation
 * goes, 确认并同步 also draws its keyframe again. */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useAssets } from "@/api/hooks/assets";
import { useComponentModels } from "@/api/hooks/config";
import { useImpactPreview } from "@/api/hooks/impact";
import { useProduct, useProducts } from "@/api/hooks/products";
import { useScript } from "@/api/hooks/script";
import { useOutputSpec, useRouteEpisode } from "@/api/hooks/series";
import { usePatchShot, useShots } from "@/api/hooks/shots";
import type { ShotPatch } from "@/api/schemas/shots";
import { paths } from "@/app/paths";
import { GateButton } from "@/components/GateButton";
import { ImpactDialog } from "@/components/ImpactDialog";
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
  const assets = useAssets(seriesId, episode?.id);
  const episodeProducts = useProducts({ owner: `episode:${episode?.id ?? ""}` });
  const patchShot = usePatchShot(episode?.id);
  const preview = useImpactPreview();
  // An edit of a confirmed shot, waiting in the impact dialog; 撤销 puts the form back.
  const [editing, setEditing] = useState<{ id: string; change: ShotPatch } | null>(null);
  const [undone, setUndone] = useState(0);
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
    const settings = Object.keys(change).some((k) => k !== "confirmed");
    if (settings && (shot.confirmed || !!plan?.locked_hash)) {
      const target = shot.id;
      preview.mutate(
        { kind: "shot_edit", target_id: target, patch: change },
        {
          onSuccess: () => setEditing({ id: target, change }),
          onError: (err) => toast.error(errorMessage(tc, err)),
        },
      );
      return;
    }
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

  const closeEdit = (kept: boolean) => {
    if (!kept) setUndone((n) => n + 1);
    setEditing(null);
    preview.reset();
  };

  return (
    <StepLayout
      inspector={
        <Inspector
          components={[
            { id: "plan", productId: plan?.id },
            { id: "kf", productId: shot?.keyframe_product_id ?? undefined },
          ]}
          item={shot ? `shot:${shot.id}` : null}
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
                key={`${shot.id}-${undone}`}
                shot={shot}
                assets={assets.data ?? []}
                aspect={aspect}
                assetsPath={paths.step(seriesId, ep, "assets")}
                lines={lines}
                scriptPath={(id) =>
                  `${paths.step(seriesId, ep, "script")}?line=${encodeURIComponent(id)}`
                }
                novelPath={(idx) => `${paths.step(seriesId, ep, "novel")}?para=${idx}`}
                busy={patchShot.isPending || preview.isPending}
                onPatch={onPatch}
              />
            </>
          ) : null
        }
      </QueryState>
      {editing && preview.data ? (
        <ImpactDialog
          variant="modal"
          impact={preview.data}
          title={t("shot.editTitle", {
            id: list.find((s) => s.id === editing.id)?.label ?? "",
          })}
          detail={editing.change.intent}
          onOpenChange={(open) => {
            if (!open) closeEdit(false);
          }}
          onResolved={(action) => closeEdit(action !== "undo")}
        />
      ) : null}
    </StepLayout>
  );
}
