/** 03 素材 · 角色、场景、道具、文字、音色 (prototype Assets.dc.html). */
import { useQueryClient } from "@tanstack/react-query";
import { Layers } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { assetKeys, useAnalyzeAssets, useAssets, useLockAsset } from "@/api/hooks/assets";
import { useComponentModels } from "@/api/hooks/config";
import { useApplyImpact, useImpactPreview } from "@/api/hooks/impact";
import { useProduct } from "@/api/hooks/products";
import { useEpisodeProgress, useOutputSpec, useRouteEpisode } from "@/api/hooks/series";
import type { Asset, AssetKind } from "@/api/schemas/assets";
import { paths } from "@/app/paths";
import { GateButton } from "@/components/GateButton";
import { ImpactDialog } from "@/components/ImpactDialog";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { StepLayout } from "@/components/StepLayout";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { AssetDetail } from "@/pages/assets/AssetDetail";
import { AssetList } from "@/pages/assets/AssetList";
import { useInspectorStore } from "@/stores/inspector";

const KINDS: AssetKind[] = ["character", "scene", "prop", "text", "voice"];
const COMPONENTS = ["img", "text", "voice"] as const;
const componentOf = (a: Asset) =>
  a.kind === "voice" ? "voice" : a.kind === "text" ? "text" : "img";

export default function AssetsPage() {
  const { t } = useTranslation("assets");
  const { t: te } = useTranslation("enums");
  const { t: tc } = useTranslation();
  const client = useQueryClient();
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const assets = useAssets(seriesId);
  const spec = useOutputSpec(seriesId);
  const progress = useEpisodeProgress(episode?.id);
  const lock = useLockAsset(seriesId, episode?.id);
  const analyze = useAnalyzeAssets(episode?.id);
  const preview = useImpactPreview();
  const apply = useApplyImpact();
  const component = useInspectorStore((s) => s.component);
  const show = useInspectorStore((s) => s.show);
  const [filter, setFilter] = useState<AssetKind | "all">("all");
  const [selectedId, setSelectedId] = useState("linwan");
  const [unlocking, setUnlocking] = useState<Asset | null>(null);

  useEffect(() => useInspectorStore.getState().reset(), []);

  const list = assets.data ?? [];
  const picked = list.find((a) => a.id === selectedId) ?? list[0];
  // An Inspector chip of another kind shows the first asset of that kind.
  const selected =
    component && picked && componentOf(picked) !== component
      ? (list.find((a) => componentOf(a) === component) ?? picked)
      : picked;
  const selectedComponent = selected ? componentOf(selected) : "img";
  const product = useProduct(selected?.product_id);
  const models = useComponentModels(selectedComponent);
  const ep = String(episodeIdx);

  const select = (a: Asset) => {
    setSelectedId(a.id);
    useInspectorStore.getState().select(componentOf(a));
  };

  const steps = progress.data?.steps.assets;
  const done = steps?.done ?? 0;
  const total = steps?.total ?? list.length;
  const summary = KINDS.map((k) =>
    t("kindCount", { kind: te(`assetKind.${k}`), count: list.filter((a) => a.kind === k).length }),
  ).join(t("summarySep"));
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const letter = (i: number) => "ABCD"[i] ?? "";

  const refresh = () => {
    void client.invalidateQueries({ queryKey: assetKeys.list(seriesId) });
    setUnlocking(null);
    preview.reset();
  };

  const startUnlock = (a: Asset) =>
    preview.mutate(
      { kind: "asset_unlock", target_id: a.id, patch: {} },
      {
        onSuccess: (impact) => {
          if (impact.lines.length) setUnlocking(a);
          else
            apply.mutate({ impact_id: impact.id, action: "mark" }, { onSuccess: refresh, onError });
        },
        onError,
      },
    );

  return (
    <StepLayout
      inspector={
        <Inspector
          components={COMPONENTS.map((id) => ({
            id,
            productId:
              id === selectedComponent
                ? selected?.product_id
                : list.find((a) => componentOf(a) === id)?.product_id,
          }))}
        />
      }
    >
      <PageHeader
        step={3}
        title={t("title")}
        lead={t("lead")}
        actions={
          <>
            <Button variant="outline" size="lg" asChild>
              <Link to={paths.sync(seriesId)}>
                <Layers aria-hidden />
                {t("sync")}
              </Link>
            </Button>
            <GateButton
              gate="assets"
              scopeId={episode?.id}
              label={t("gate")}
              to={paths.step(seriesId, ep, "storyboard")}
            />
          </>
        }
      />

      {assets.data ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-card px-4 py-3">
          <span className="text-sm font-medium tabular-nums">{t("progress", { done, total })}</span>
          <Progress
            value={total ? (done / total) * 100 : 0}
            aria-label={t("progress", { done, total })}
            className="w-40"
          />
          <span className="text-xs text-muted-foreground">{t("analyzed", { summary })}</span>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            disabled={analyze.isPending}
            onClick={() =>
              analyze.mutate(undefined, {
                onSuccess: (r) =>
                  toast.info(r.added || r.changed ? t("reanalyzedChanged", r) : t("reanalyzed")),
                onError,
              })
            }
          >
            {t("reanalyze")}
          </Button>
        </div>
      ) : null}

      {product.data && selected ? (
        <RunBar
          product={product.data}
          what={t(
            `what.${selected.kind === "voice" ? "voice" : selected.kind === "text" ? "text" : "image"}`,
            {
              name: selected.name,
            },
          )}
          models={models}
          onEditPrompt={() => show("prompt", selectedComponent)}
          onOpenHistory={() => show("history", selectedComponent)}
        />
      ) : null}

      <QueryState query={assets} skeleton={<Skeleton className="h-96 w-full" />}>
        {(all) =>
          selected ? (
            <div className="grid items-start gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
              <AssetList
                assets={all}
                kinds={KINDS}
                filter={filter}
                onFilter={setFilter}
                selectedId={selected.id}
                onSelect={select}
              />
              <AssetDetail
                key={selected.id}
                asset={selected}
                seriesId={seriesId}
                aspect={spec.data?.aspect ?? "9:16"}
                storyboardPath={paths.step(seriesId, ep, "storyboard")}
                busy={lock.isPending || preview.isPending}
                onLock={() =>
                  lock.mutate(selected.id, {
                    onSuccess: (a) =>
                      toast.success(
                        t(a.kind === "character" ? "detail.lockedCharacter" : "detail.locked", {
                          name: a.name,
                          letter: letter(a.pick),
                        }),
                      ),
                    onError,
                  })
                }
                onUnlock={() => startUnlock(selected)}
              />
            </div>
          ) : null
        }
      </QueryState>

      {unlocking && preview.data ? (
        <ImpactDialog
          variant="modal"
          impact={preview.data}
          title={t("detail.unlockTitle", { name: unlocking.name })}
          onOpenChange={(open) => {
            if (!open) {
              setUnlocking(null);
              preview.reset();
            }
          }}
          onResolved={refresh}
        />
      ) : null}
    </StepLayout>
  );
}
