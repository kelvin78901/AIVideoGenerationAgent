/** 01 小说 · 导入与补全 (prototype Main.dc.html). */
import { BookOpen, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { useComponentModels } from "@/api/hooks/config";
import { useBible, useNovel, useSuggestions } from "@/api/hooks/novel";
import { useProducts } from "@/api/hooks/products";
import type { BibleEntity } from "@/api/schemas/novel";
import { useEpisodeProgress, useEpisodes, useRouteEpisode } from "@/api/hooks/series";
import { paths } from "@/app/paths";
import { EmptyState } from "@/components/EmptyState";
import { GateButton } from "@/components/GateButton";
import { ImpactGuard } from "@/components/ImpactGuard";
import { Inspector } from "@/components/Inspector";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { StepLayout } from "@/components/StepLayout";
import { Button } from "@/components/ui/button";
import { useInspectorStore } from "@/stores/inspector";
import { BiblePanel } from "@/pages/novel/BiblePanel";
import { ImportDialog } from "@/pages/novel/ImportDialog";
import { ScriptTrace } from "@/pages/novel/ScriptTrace";
import { SourceText, type NovelView } from "@/pages/novel/SourceText";
import { SuggestionList } from "@/pages/novel/SuggestionList";
import { chapterOf } from "@/pages/novel/text";

const COMPONENTS = ["enrich", "extract"] as const;

export default function NovelPage() {
  const { t } = useTranslation("novel");
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const products = useProducts({ owner: `series:${seriesId}` });
  const [chapter, setChapter] = useState(0);
  const novel = useNovel(seriesId, chapter);
  const suggestions = useSuggestions(seriesId);
  const bible = useBible(seriesId);
  const episodes = useEpisodes(seriesId);
  const progress = useEpisodeProgress(episode?.id);
  const selected = useInspectorStore((s) => s.component) ?? COMPONENTS[0];
  const show = useInspectorStore((s) => s.show);
  const models = useComponentModels(selected);
  const enrichModels = useComponentModels("enrich");
  const [view, setView] = useState<NovelView>("diff");
  const [focus, setFocus] = useState<number | null>(0);
  // The paragraph to bring into view (a suggestion's, or the first of a bible entry's).
  const [target, setTarget] = useState<number | null>(0);
  const [entity, setEntity] = useState<BibleEntity | null>(null);
  const [importing, setImporting] = useState(false);
  // 「在剧本里」 of one paragraph (段落 → 剧本行).
  const [traced, setTraced] = useState<number | null>(null);
  // The script page and a shot link here with `?para=` (0-based).
  const [search] = useSearchParams();
  const linked = search.get("para");

  useEffect(() => useInspectorStore.getState().reset(), []);
  // A paragraph in another chapter switches chapters first; scroll once it is on screen.
  const shown = novel.data?.paragraphs.some((p) => p.idx === target);
  useEffect(() => {
    if (target != null && shown)
      document.getElementById(`novel-para-${target}`)?.scrollIntoView?.({ block: "nearest" });
  }, [target, shown]);

  const productOf = (component: string) => products.data?.find((p) => p.component_id === component);
  const product = productOf(selected);
  // An edit turns what was built from the novel stale. Once the novel (or a script built on it)
  // is confirmed, edits preview their impact first.
  const novelProduct = products.data?.find((p) => p.slot === "novel");
  const confirmed = progress.data?.steps.novel?.state === "confirmed";
  const guarded = confirmed || !!episodes.data?.some((e) => e.script_status === "confirmed");
  const downstream = COMPONENTS.some((c) => productOf(c)?.adopted_version_id);
  const ep = String(episodeIdx);
  const count = (kind: string) => bible.data?.entities.filter((e) => e.kind === kind).length ?? 0;
  const what =
    selected === "enrich"
      ? t("what.enrich", { count: suggestions.data?.suggestions.length ?? 0 })
      : t("what.extract", {
          characters: count("character"),
          locations: count("location"),
          props: count("prop"),
        });

  const showPara = (idx: number) => {
    setTarget(idx);
    const shownIn = chapterOf(novel.data?.chapters ?? [], idx);
    if (shownIn && shownIn.idx !== chapter) setChapter(shownIn.idx);
  };
  // A `?para=` link (once the chapters are known): focus it and open 「在剧本里」.
  const [seenLink, setSeenLink] = useState<string | null>(null);
  if (linked !== null && linked !== seenLink && novel.data) {
    setSeenLink(linked);
    const idx = Number(linked);
    if (Number.isInteger(idx) && idx >= 0) {
      setFocus(idx);
      setTraced(idx);
      showPara(idx);
    }
  }
  const focusPara = (idx: number) => {
    setFocus(idx);
    showPara(idx);
  };
  const selectEntity = (e: BibleEntity | null) => {
    setEntity(e);
    setFocus(null);
    const first = e?.paras[0];
    if (first !== undefined) showPara(first);
  };
  const source = novel.data?.source;
  const empty = novel.data != null && source == null;

  return (
    <ImpactGuard active={guarded}>
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
              <Button variant="outline" size="lg" onClick={() => setImporting(true)}>
                <Upload aria-hidden />
                {t("import")}
              </Button>
              <GateButton
                gate="novel"
                episodeId={episode?.id}
                label={t("gate")}
                to={paths.step(seriesId, ep, "script")}
              />
            </>
          }
        />

        {empty ? (
          <EmptyState
            icon={BookOpen}
            title={t("empty.title")}
            description={t("empty.lead")}
            className="py-14"
            action={
              <Button size="lg" onClick={() => setImporting(true)}>
                <Upload aria-hidden />
                {t("empty.action")}
              </Button>
            }
          />
        ) : (
          <>
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
                    seriesId={seriesId}
                    novel={n}
                    suggestions={suggestions.data?.suggestions ?? []}
                    view={view}
                    onViewChange={setView}
                    onChapterChange={setChapter}
                    focus={focus}
                    marked={entity?.paras}
                    editable={novelProduct !== undefined}
                    downstream={downstream}
                    traced={traced}
                    onTrace={setTraced}
                    trace={(idx) => (
                      <ScriptTrace
                        seriesId={seriesId}
                        para={idx}
                        episodes={episodes.data ?? []}
                        onClose={() => setTraced(null)}
                      />
                    )}
                  />
                )}
              </QueryState>
              <QueryState query={suggestions} skeleton={<Skeleton className="h-96 w-full" />}>
                {(data) => (
                  <SuggestionList
                    seriesId={seriesId}
                    suggestions={data.suggestions}
                    adopted={data.adopted}
                    locked={!!productOf("enrich")?.locked_hash}
                    models={enrichModels}
                    onFocus={focusPara}
                  />
                )}
              </QueryState>
            </div>

            <QueryState query={bible} skeleton={<Skeleton className="h-32 w-full" />}>
              {(b) => (
                <BiblePanel
                  seriesId={seriesId}
                  bible={b}
                  assetsPath={paths.step(seriesId, ep, "assets")}
                  selected={entity?.id ?? null}
                  onSelect={selectEntity}
                />
              )}
            </QueryState>
          </>
        )}

        <ImportDialog
          seriesId={seriesId}
          current={source ?? null}
          open={importing}
          onOpenChange={setImporting}
          onImported={() => {
            setChapter(0);
            setFocus(0);
            setTarget(0);
            setEntity(null);
          }}
        />
      </StepLayout>
    </ImpactGuard>
  );
}
