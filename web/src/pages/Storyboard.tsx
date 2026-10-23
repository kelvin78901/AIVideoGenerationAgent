/** 04 分镜 · 关键帧与镜头设定 (prototype Storyboard.dc.html). The shots show as a board or a
 * table (`?view=table`), the selected one is `?shot=` in both. A confirmed shot (or a shot of a
 * confirmed storyboard) is changed, split or merged through the impact preview (`shot_edit`):
 * its confirmation goes, 确认并同步 also draws its keyframe again. */
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
import { useMergeShot, usePatchShot, useShots, useSplitShot } from "@/api/hooks/shots";
import type { Shot, ShotEdit, ShotPatch } from "@/api/schemas/shots";
import { paths } from "@/app/paths";
import { GateButton } from "@/components/GateButton";
import { ImpactDialog } from "@/components/ImpactDialog";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StepLayout } from "@/components/StepLayout";
import { scriptBlocks, useBlockLead } from "@/pages/script/blocks";
import { PreviewStrip } from "@/pages/storyboard/PreviewStrip";
import { ShotCards } from "@/pages/storyboard/ShotCards";
import { ShotSettings } from "@/pages/storyboard/ShotSettings";
import { ShotTable } from "@/pages/storyboard/ShotTable";
import { useInspectorStore } from "@/stores/inspector";

type View = "board" | "table";

/** What the user does to a shot: change its settings, split it (after a line), merge it with
 * the next shot of its scene. */
type Edit =
  { kind: "patch"; change: ShotPatch } | { kind: "split"; after?: string } | { kind: "merge" };

export default function StoryboardPage() {
  const { t } = useTranslation("storyboard");
  const { t: tc } = useTranslation();
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const shots = useShots(episode?.id);
  const spec = useOutputSpec(seriesId);
  const assets = useAssets(seriesId, episode?.id);
  const episodeProducts = useProducts({ owner: `episode:${episode?.id ?? ""}` });
  const patchShot = usePatchShot(episode?.id);
  const splitShot = useSplitShot(episode?.id);
  const mergeShot = useMergeShot(episode?.id);
  const preview = useImpactPreview();
  // An edit of a confirmed shot, waiting in the impact dialog; 撤销 (or a refused edit) puts
  // the form back.
  const [editing, setEditing] = useState<{ id: string; change: ShotEdit } | null>(null);
  const [undone, setUndone] = useState(0);
  const component = useInspectorStore((s) => s.component) ?? "kf";
  const show = useInspectorStore((s) => s.show);
  const models = useComponentModels(component);
  const script = useScript(episode?.id);
  const leadOf = useBlockLead();
  // A script line's 「镜头 1-04」 links here with `?shot=`; picking a shot (on the board or in the
  // table) writes it there, so both views and a reload keep it.
  const [search, setSearch] = useSearchParams();
  const selectedId = search.get("shot");
  const view: View = search.get("view") === "table" ? "table" : "board";
  const setParam = (key: string, value: string | null) =>
    setSearch(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value === null) next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  const setSelectedId = (id: string) => setParam("shot", id);

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

  const fail = (err: unknown) => {
    toast.error(errorMessage(tc, err));
    setUndone((n) => n + 1);
  };

  const edit = (target: Shot, e: Edit) => {
    const next = list[list.indexOf(target) + 1];
    const settles = e.kind !== "patch" || Object.keys(e.change).some((k) => k !== "confirmed");
    const confirmed =
      target.confirmed ||
      !!plan?.locked_hash ||
      (e.kind === "merge" && next?.scene_id === target.scene_id && next.confirmed);
    if (settles && confirmed) {
      const change: ShotEdit =
        e.kind === "patch"
          ? e.change
          : e.kind === "split"
            ? { split: { after_line_id: e.after ?? null } }
            : { merge: true };
      preview.mutate(
        { kind: "shot_edit", target_id: target.id, patch: change },
        { onSuccess: () => setEditing({ id: target.id, change }), onError: fail },
      );
      return;
    }
    if (e.kind === "split") {
      splitShot.mutate(
        { id: target.id, afterLineId: e.after },
        {
          onSuccess: (now) => {
            const at = now.findIndex((s) => s.id === target.id);
            toast.success(t("shot.splitDone", { id: now[at]?.label, next: now[at + 1]?.label }));
          },
          onError: fail,
        },
      );
      return;
    }
    if (e.kind === "merge") {
      mergeShot.mutate(target.id, {
        onSuccess: () => toast.success(t("shot.mergeDone", { id: target.label })),
        onError: fail,
      });
      return;
    }
    const { change } = e;
    patchShot.mutate(
      { id: target.id, patch: change },
      {
        onSuccess: (s) => {
          if (change.confirmed !== undefined)
            toast.success(
              t(change.confirmed ? "shot.confirmed" : "shot.unconfirmed", { id: s.label }),
            );
        },
        onError: fail,
      },
    );
  };
  const busy =
    patchShot.isPending || splitShot.isPending || mergeShot.isPending || preview.isPending;

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
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-bold">
                  {t("list.title", { count: list.length, seconds })}
                </h2>
                <SegmentedControl
                  className="ml-auto"
                  size="sm"
                  label={t("list.views")}
                  value={view}
                  onChange={(v) => setParam("view", v === "table" ? "table" : null)}
                  options={(["board", "table"] as const).map((v) => ({
                    value: v,
                    label: t(`list.view.${v}`),
                  }))}
                />
              </div>
              {view === "table" ? (
                <ShotTable
                  shots={list}
                  assets={assets.data ?? []}
                  selectedId={shot.id}
                  busy={busy}
                  onSelect={setSelectedId}
                  onPatch={(target, change) => edit(target, { kind: "patch", change })}
                  onSplit={(target) => edit(target, { kind: "split" })}
                  onMerge={(target) => edit(target, { kind: "merge" })}
                />
              ) : (
                <ShotCards
                  shots={list}
                  aspect={aspect}
                  selectedId={shot.id}
                  onSelect={setSelectedId}
                />
              )}
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
                busy={busy}
                canMerge={list[list.indexOf(shot) + 1]?.scene_id === shot.scene_id}
                onPatch={(change) => edit(shot, { kind: "patch", change })}
                onSplit={(after) => edit(shot, { kind: "split", after })}
                onMerge={() => edit(shot, { kind: "merge" })}
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
