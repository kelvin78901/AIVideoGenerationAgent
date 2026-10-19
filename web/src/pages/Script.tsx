/** 02 剧本 · 分集与剧本化 (prototype Script.dc.html). */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useComponentModels } from "@/api/hooks/config";
import { useApplyImpact, useImpactPreview } from "@/api/hooks/impact";
import { useNovel, useSuggestions } from "@/api/hooks/novel";
import { useProducts } from "@/api/hooks/products";
import { scriptKeys, useRewriteBlock, useScript } from "@/api/hooks/script";
import { useEpisodes, useRouteEpisode } from "@/api/hooks/series";
import type { Episode } from "@/api/schemas/episodes";
import type { Product } from "@/api/schemas/products";
import { paths } from "@/app/paths";
import { GateButton } from "@/components/GateButton";
import { ImpactDialog } from "@/components/ImpactDialog";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StepLayout } from "@/components/StepLayout";
import { useRunAction } from "@/components/useRunAction";
import { Button } from "@/components/ui/button";
import { modelName } from "@/lib/versions";
import { scriptBlocks, type Block } from "@/pages/script/blocks";
import { EpisodeCards } from "@/pages/script/EpisodeCards";
import { ScriptScreenplay, ScriptTable } from "@/pages/script/ScriptView";
import { useInspectorStore } from "@/stores/inspector";

type View = "script" | "table";

/** An episode without a script yet: 「生成这一集的剧本」. */
function GenerateEpisode({ episode, product }: { episode: Episode; product: Product | undefined }) {
  const { t } = useTranslation("script");
  const action = useRunAction(product?.id ?? "");
  const name = t("episodes.name", { n: episode.idx, title: episode.title });
  const draft = episode.script_status === "draft";
  const busy = action.pending || !!product?.running;
  return (
    <section className="flex flex-col items-start gap-2.5 rounded-lg border bg-card p-5">
      <h2 className="text-base font-bold">{t("other.title", { name })}</h2>
      <p className="text-sm text-muted-foreground">{t(draft ? "other.draft" : "other.none")}</p>
      <Button
        disabled={!product || busy}
        onClick={() => {
          useInspectorStore.getState().select("script");
          action.run({ mode: product?.versions.length ? "rerun" : "run" });
        }}
      >
        {t(draft ? "other.regenerate" : "other.generate")}
      </Button>
    </section>
  );
}

export default function ScriptPage() {
  const { t } = useTranslation("script");
  const { t: tc } = useTranslation();
  const client = useQueryClient();
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const episodes = useEpisodes(seriesId);
  const novel = useNovel(seriesId);
  const suggestions = useSuggestions(seriesId);
  const script = useScript(episode?.id);
  const seriesProducts = useProducts({ owner: `series:${seriesId}` });
  const episodeProducts = useProducts({ owner: `episode:${episode?.id ?? ""}` });
  const selected = useInspectorStore((s) => s.component) ?? "script";
  const show = useInspectorStore((s) => s.show);
  const models = useComponentModels(selected);
  const scriptModels = useComponentModels("script");
  const preview = useImpactPreview();
  const apply = useApplyImpact();
  const rewrite = useRewriteBlock();
  const [view, setView] = useState<View>("script");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pending, setPending] = useState<{ block: Block; text: string } | null>(null);

  useEffect(() => {
    useInspectorStore.getState().reset();
    useInspectorStore.getState().select("script");
  }, []);

  const split = seriesProducts.data?.find((p) => p.component_id === "split");
  const scriptProduct = episodeProducts.data?.find((p) => p.component_id === "script");
  const product = selected === "split" ? split : scriptProduct;
  const ep = String(episodeIdx);

  const blocks =
    script.data && novel.data
      ? scriptBlocks(script.data, novel.data.paragraphs).map((b) =>
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

  /** A confirmed block changed: preview the impact first; nothing is saved until 标记 / 重跑. */
  const startChange = (block: Block, text: string) => {
    if (text === block.text) return;
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

  const settle = async () => {
    await client.invalidateQueries({ queryKey: scriptKeys.script(episode?.id ?? "") });
    setPending(null);
    preview.reset();
  };

  const leadOf = (b: Block) =>
    b.kind === "action"
      ? t("script.actionMark")
      : b.kind === "dialogue" || b.kind === "vo"
        ? t("script.speaker", { who: b.line.character_name ?? "", tone: b.line.tone ?? "" })
        : "";

  return (
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
        {(list) => <EpisodeCards episodes={list} seriesId={seriesId} currentIdx={episodeIdx} />}
      </QueryState>

      {product ? (
        <RunBar
          product={product}
          what={what}
          models={models}
          onEditPrompt={() => show("prompt", selected)}
          onOpenHistory={() => show("history", selected)}
        />
      ) : null}

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
              {view === "script" ? (
                <ScriptScreenplay
                  blocks={blocks}
                  paragraphs={paragraphs}
                  selectedId={activeId}
                  pendingId={pending?.block.id ?? null}
                  rewritingId={rewrite.isPending ? (rewrite.variables?.id ?? null) : null}
                  locked={pending !== null}
                  models={scriptModels}
                  routeModel={scriptProduct?.estimate?.model_key}
                  onSelect={setSelectedId}
                  actions={{
                    onSave: startChange,
                    onRewrite: (block, model) =>
                      rewrite.mutate(
                        { id: block.id, scene: block.kind === "scene", model },
                        {
                          onSuccess: (proposal) => {
                            toast.success(
                              t("script.rewritten", {
                                model: modelName(scriptModels, proposal.model_key),
                              }),
                            );
                            startChange(block, proposal.text);
                          },
                          onError,
                        },
                      ),
                  }}
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
  );
}
