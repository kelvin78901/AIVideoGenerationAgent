/** 02 剧本 · 分集与剧本化 (prototype Script.dc.html). */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { toast } from "sonner";

import { ApiError, errorMessage } from "@/api/client";
import { useComponentModels } from "@/api/hooks/config";
import { useApplyImpact, useImpactPreview } from "@/api/hooks/impact";
import { useNovel, useSuggestions } from "@/api/hooks/novel";
import { useProducts } from "@/api/hooks/products";
import { scriptKeys, usePatchBlock, useRewriteBlock, useScript } from "@/api/hooks/script";
import { useEpisodes, useRouteEpisode } from "@/api/hooks/series";
import { useShots } from "@/api/hooks/shots";
import type { Episode } from "@/api/schemas/episodes";
import type { Product } from "@/api/schemas/products";
import { paths } from "@/app/paths";
import { GateButton } from "@/components/GateButton";
import { ImpactDialog } from "@/components/ImpactDialog";
import { ImpactGuard } from "@/components/ImpactGuard";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StepLayout } from "@/components/StepLayout";
import { useRunAction } from "@/components/useRunAction";
import { Button } from "@/components/ui/button";
import { modelName } from "@/lib/versions";
import { scriptBlocks, useBlockLead, type Block } from "@/pages/script/blocks";
import { Episodes, type EpisodeView } from "@/pages/script/Episodes";
import {
  ScriptScreenplay,
  ScriptTable,
  type OverBudget,
  type ScriptLinks,
} from "@/pages/script/ScriptView";
import { useInspectorStore } from "@/stores/inspector";

type View = "script" | "table";

/** An episode without a script yet: 「生成这一集的剧本」. */
function GenerateEpisode({ episode, product }: { episode: Episode; product: Product | undefined }) {
  const { t } = useTranslation("script");
  const action = useRunAction(product?.id ?? "");
  const name = t("episodes.name", { n: episode.idx, title: episode.title });
  const busy = action.pending || !!product?.running;
  return (
    <section className="flex flex-col items-start gap-2.5 rounded-lg border bg-card p-5">
      <h2 className="text-base font-bold">{t("other.title", { name })}</h2>
      <p className="text-sm text-muted-foreground">{t("other.none")}</p>
      <Button
        disabled={!product || busy}
        onClick={() => {
          useInspectorStore.getState().select("script");
          action.run({ mode: product?.versions.length ? "rerun" : "run" });
        }}
      >
        {t("other.generate")}
      </Button>
    </section>
  );
}

export default function ScriptPage() {
  const { t } = useTranslation("script");
  const { t: tc } = useTranslation();
  const client = useQueryClient();
  const [search] = useSearchParams();
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const episodes = useEpisodes(seriesId);
  const novel = useNovel(seriesId);
  const suggestions = useSuggestions(seriesId);
  const script = useScript(episode?.id);
  const shots = useShots(episode?.id);
  const seriesProducts = useProducts({ owner: `series:${seriesId}` });
  const episodeProducts = useProducts({ owner: `episode:${episode?.id ?? ""}` });
  const selected = useInspectorStore((s) => s.component) ?? "script";
  const show = useInspectorStore((s) => s.show);
  const models = useComponentModels(selected);
  const scriptModels = useComponentModels("script");
  const preview = useImpactPreview();
  const apply = useApplyImpact();
  const patchBlock = usePatchBlock(seriesId);
  const rewrite = useRewriteBlock();
  const leadOf = useBlockLead();
  const [view, setView] = useState<View>("script");
  const [episodeView, setEpisodeView] = useState<EpisodeView>("cards");
  // 「在剧本里」 on the novel page and a shot's lines link here with `?line=`; a block the user
  // picks wins until the link changes.
  const linked = search.get("line");
  const [picked, setPicked] = useState<{ id: string; link: string | null } | null>(null);
  const selectedId = picked && picked.link === linked ? picked.id : linked;
  const [pending, setPending] = useState<{ block: Block; text: string } | null>(null);
  const [overBudget, setOverBudget] = useState<OverBudget | null>(null);

  useEffect(() => {
    useInspectorStore.getState().reset();
    useInspectorStore.getState().select("script");
  }, []);
  const loaded = !!script.data;
  useEffect(() => {
    if (loaded && linked) document.querySelector(`[data-block="${linked}"]`)?.scrollIntoView?.();
  }, [loaded, linked]);

  const split = seriesProducts.data?.find((p) => p.component_id === "split");
  const scriptProduct = episodeProducts.data?.find((p) => p.component_id === "script");
  const product = selected === "split" ? split : scriptProduct;
  const splitAction = useRunAction(split?.id ?? "");
  const ep = String(episodeIdx);
  // A confirmed script shows the impact of an edit first; a draft is edited in place.
  const confirmed = episode?.script_status === "confirmed";

  const blocks = script.data
    ? scriptBlocks(script.data).map((b) =>
        b.id === pending?.block.id ? { ...b, text: pending.text } : b,
      )
    : [];
  const paragraphs =
    novel.data?.paragraphs.map(
      (p) =>
        p.text +
        (suggestions.data?.suggestions ?? [])
          .filter((s) => s.status === "accepted" && s.para_idx === p.idx)
          .map((s) => s.text)
          .join(""),
    ) ?? [];
  const activeId = selectedId ?? blocks.find((b) => b.kind !== "scene")?.id ?? null;
  const aiCount = blocks.filter((b) => b.kind !== "scene" && b.line.ai_added).length;
  const sceneCount = blocks.filter((b) => b.kind === "scene").length;

  const links: ScriptLinks = {
    shotsOf: (b) => (shots.data ?? []).filter((s) => s.line_ids.includes(b.id)),
    shot: (id) => `${paths.step(seriesId, ep, "storyboard")}?shot=${encodeURIComponent(id)}`,
    para: (idx) => `${paths.step(seriesId, ep, "novel")}?para=${idx}`,
  };

  const what =
    selected === "split"
      ? t("what.split", { count: episodes.data?.length ?? 0 })
      : blocks.length && episode
        ? t("what.script", {
            n: episode.idx,
            from: episode.scene_from,
            to: episode.scene_to,
            count: blocks.length,
          })
        : t("what.scriptEmpty", { n: episodeIdx });

  const onError = (err: unknown) => toast.error(errorMessage(tc, err));

  const settle = async () => {
    await client.invalidateQueries({ queryKey: scriptKeys.script(episode?.id ?? "") });
    setPending(null);
    preview.reset();
  };

  /** A draft is saved right away; a confirmed block previews the impact first (nothing is
   * saved until 标记 / 重跑). */
  const startChange = (block: Block, text: string) => {
    if (text === block.text) return;
    if (!confirmed) {
      patchBlock.mutate(
        { id: block.id, scene: block.kind === "scene", text },
        { onSuccess: () => toast.success(t("script.saved")), onError },
      );
      return;
    }
    setPending({ block, text });
    preview.mutate(
      {
        kind: block.kind === "scene" ? "scene_edit" : "line_edit",
        target_id: block.id,
        patch: { text },
      },
      {
        onSuccess: (impact) => {
          // Nothing downstream yet: save without asking.
          if (impact.lines.length === 0)
            apply.mutate(
              { impact_id: impact.id, action: "mark" },
              { onSuccess: () => void settle(), onError },
            );
        },
        onError: (err) => {
          setPending(null);
          onError(err);
        },
      },
    );
  };

  const startRewrite = (block: Block, model?: string, confirmBudget = false) => {
    setOverBudget(null);
    rewrite.mutate(
      { id: block.id, scene: block.kind === "scene", model, confirm_budget: confirmBudget },
      {
        onSuccess: (proposal) => {
          toast.success(
            t("script.rewritten", { model: modelName(scriptModels, proposal.model_key) }),
          );
          startChange(block, proposal.text);
        },
        // Over the per-call cap or the episode's budget: ask first (hard rule 6).
        onError: (err) =>
          err instanceof ApiError && err.code === "over_budget"
            ? setOverBudget({ blockId: block.id, model, message: errorMessage(tc, err) })
            : onError(err),
      },
    );
  };

  return (
    // Moving or editing a beat of a confirmed script previews its impact (BeatBoard).
    <ImpactGuard active={!!episodes.data?.some((e) => e.script_status === "confirmed")}>
      <StepLayout
        inspector={
          <Inspector
            components={[
              { id: "split", productId: split?.id },
              { id: "script", productId: scriptProduct?.id },
            ]}
          />
        }
      >
        <PageHeader
          step={2}
          title={t("title")}
          lead={t("lead")}
          actions={
            <GateButton
              gate="script"
              episodeId={episode?.id}
              label={t("gate")}
              to={paths.step(seriesId, ep, "assets")}
            />
          }
        />

        <QueryState query={episodes} skeleton={<Skeleton className="h-28 w-full" />}>
          {(list) => (
            <Episodes
              seriesId={seriesId}
              episodes={list}
              currentIdx={episodeIdx}
              split={split}
              view={episodeView}
              onViewChange={(v) => {
                setEpisodeView(v);
                // The board is 分集规划's: its RunBar and Inspector come along.
                useInspectorStore.getState().select(v === "board" ? "split" : "script");
              }}
              onRunSplit={() => {
                useInspectorStore.getState().select("split");
                splitAction.run({ mode: split?.versions.length ? "rerun" : "run" });
              }}
              onOpenHistory={() => show("history", "split")}
            />
          )}
        </QueryState>

        {product ? (
          <RunBar
            product={product}
            what={what}
            models={models}
            onEditPrompt={() => show("prompt", selected)}
            onOpenHistory={() => show("history", selected)}
          />
        ) : (
          <QueryState
            query={selected === "split" ? seriesProducts : episodeProducts}
            skeleton={<Skeleton className="h-14 w-full" />}
          >
            {() => null}
          </QueryState>
        )}

        {pending && preview.data ? (
          <ImpactDialog
            impact={preview.data}
            title={t("script.impactTitle")}
            detail={t("script.impactWhat", { text: leadOf(pending.block) + pending.text })}
            onResolved={(action) => {
              if (action === "undo") {
                setPending(null);
                preview.reset();
              } else void settle();
            }}
          />
        ) : null}

        <QueryState query={script} skeleton={<Skeleton className="h-96 w-full" />}>
          {(s) =>
            s.scenes.length === 0 ? (
              episode ? (
                <GenerateEpisode episode={episode} product={scriptProduct} />
              ) : null
            ) : (
              <section aria-labelledby="script-title" className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  <h2 id="script-title" className="text-base font-bold">
                    {t("script.title", { n: episodeIdx })}
                  </h2>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {t("script.meta", { scenes: sceneCount, blocks: blocks.length, ai: aiCount })}
                  </span>
                  <SegmentedControl
                    className="ml-auto"
                    size="sm"
                    label={t("script.views")}
                    value={view}
                    onChange={setView}
                    options={(["script", "table"] as const).map((v) => ({
                      value: v,
                      label: t(`script.view.${v}`),
                    }))}
                  />
                </div>
                {!s.adopted ? (
                  <div
                    role="status"
                    className="flex flex-wrap items-center gap-2 rounded-md border border-tone-warn-border bg-tone-warn-bg px-3 py-2 text-sm text-tone-warn-fg"
                  >
                    <span>{t("script.unadopted")}</span>
                    <Button
                      size="sm"
                      variant="outline"
                      className="ml-auto"
                      onClick={() => show("history", "script")}
                    >
                      {t("script.openHistory")}
                    </Button>
                  </div>
                ) : null}
                {view === "script" ? (
                  <ScriptScreenplay
                    blocks={blocks}
                    paragraphs={paragraphs}
                    selectedId={activeId}
                    pendingId={pending?.block.id ?? null}
                    rewritingId={rewrite.isPending ? (rewrite.variables?.id ?? null) : null}
                    locked={pending !== null || patchBlock.isPending}
                    confirmed={confirmed}
                    models={scriptModels}
                    routeModel={scriptProduct?.estimate?.model_key}
                    overBudget={overBudget}
                    links={links}
                    onSelect={(id) => {
                      setPicked({ id, link: linked });
                      if (overBudget?.blockId !== id) setOverBudget(null);
                    }}
                    actions={{ onSave: startChange, onRewrite: startRewrite }}
                  />
                ) : (
                  <ScriptTable
                    blocks={blocks}
                    selectedId={activeId}
                    pendingId={pending?.block.id ?? null}
                  />
                )}
              </section>
            )
          }
        </QueryState>
      </StepLayout>
    </ImpactGuard>
  );
}
