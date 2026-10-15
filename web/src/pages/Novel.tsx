/** 01 小说 · 导入与补全 (prototype Main.dc.html). */
import { Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useComponentModels } from "@/api/hooks/config";
import { useBible, useNovel, useSuggestions } from "@/api/hooks/novel";
import { useProducts } from "@/api/hooks/products";
import { useRouteEpisode } from "@/api/hooks/series";
import { paths } from "@/app/paths";
import { GateButton } from "@/components/GateButton";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { StepLayout } from "@/components/StepLayout";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useInspectorStore } from "@/stores/inspector";
import { BiblePanel } from "@/pages/novel/BiblePanel";
import { SourceText, type NovelView } from "@/pages/novel/SourceText";
import { SuggestionList } from "@/pages/novel/SuggestionList";

const COMPONENTS = ["enrich", "extract"] as const;

export default function NovelPage() {
  const { t } = useTranslation("novel");
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const products = useProducts({ owner: `series:${seriesId}` });
  const novel = useNovel(seriesId);
  const suggestions = useSuggestions(seriesId);
  const bible = useBible(seriesId);
  const selected = useInspectorStore((s) => s.component) ?? COMPONENTS[0];
  const show = useInspectorStore((s) => s.show);
  const models = useComponentModels(selected);
  const enrichModels = useComponentModels("enrich");
  const [view, setView] = useState<NovelView>("diff");
  const [focus, setFocus] = useState<number | null>(0);

  useEffect(() => useInspectorStore.getState().reset(), []);

  const productOf = (component: string) => products.data?.find((p) => p.component_id === component);
  const product = productOf(selected);
  const ep = String(episodeIdx);
  const count = (kind: string) => bible.data?.filter((e) => e.kind === kind).length ?? 0;
  const what =
    selected === "enrich"
      ? t("what.enrich", { count: suggestions.data?.length ?? 0 })
      : t("what.extract", {
          characters: count("character"),
          locations: count("location"),
          props: count("prop"),
        });

  const focusPara = (idx: number) => {
    setFocus(idx);
    document.getElementById(`novel-para-${idx}`)?.scrollIntoView?.({ block: "nearest" });
  };

  return (
    <StepLayout
      inspector={
        <Inspector components={COMPONENTS.map((id) => ({ id, productId: productOf(id)?.id }))} />
      }
    >
      <PageHeader
        step={1}
        title={t("title")}
        lead={t("lead")}
        actions={
          <>
            <Tooltip>
              <TooltipTrigger asChild>
                <span tabIndex={0}>
                  <Button variant="outline" size="lg" disabled>
                    <Upload aria-hidden />
                    {t("import")}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>{t("importHint")}</TooltipContent>
            </Tooltip>
            <GateButton
              gate="novel"
              episodeId={episode?.id}
              label={t("gate")}
              to={paths.step(seriesId, ep, "script")}
            />
          </>
        }
      />

      {product ? (
        <RunBar
          product={product}
          what={what}
          models={models}
          onEditPrompt={() => show("prompt", selected)}
          onOpenHistory={() => show("history", selected)}
        />
      ) : (
        <QueryState query={products} skeleton={<Skeleton className="h-14 w-full" />}>
          {() => null}
        </QueryState>
      )}

      <div className="grid items-start gap-4 xl:grid-cols-2">
        <QueryState query={novel} skeleton={<Skeleton className="h-96 w-full" />}>
          {(n) => (
            <SourceText
              novel={n}
              suggestions={suggestions.data ?? []}
              view={view}
              onViewChange={setView}
              focus={focus}
            />
          )}
        </QueryState>
        <QueryState query={suggestions} skeleton={<Skeleton className="h-96 w-full" />}>
          {(list) => (
            <SuggestionList
              seriesId={seriesId}
              suggestions={list}
              models={enrichModels}
              onFocus={focusPara}
            />
          )}
        </QueryState>
      </div>

      <QueryState query={bible} skeleton={<Skeleton className="h-32 w-full" />}>
        {(entities) => (
          <BiblePanel entities={entities} assetsPath={paths.step(seriesId, ep, "assets")} />
        )}
      </QueryState>
    </StepLayout>
  );
}
