import { ArrowLeftRight, RotateCw } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useComponentModels } from "@/api/hooks/config";
import { useProduct } from "@/api/hooks/products";
import { paths } from "@/app/paths";
import { Chip } from "@/components/Chip";
import { CostBadge } from "@/components/CostBadge";
import { EmptyState } from "@/components/EmptyState";
import { ModelPicker } from "@/components/ModelPicker";
import { ModelSwitchMenu } from "@/components/ModelSwitchMenu";
import { PromptEditor } from "@/components/PromptEditor";
import { QueryState } from "@/components/QueryState";
import { ShotWorkflow } from "@/components/ShotWorkflow";
import { useRunAction } from "@/components/useRunAction";
import { VersionHistory } from "@/components/VersionHistory";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { currentVersion } from "@/lib/versions";
import { useInspectorStore, type InspectorTab } from "@/stores/inspector";

export interface InspectorComponent {
  /** components.yaml id (`enrich`, `kf` …). */
  id: string;
  /** The product this component produces for the current selection; undefined = none yet. */
  productId?: string;
}

/**
 * Right-hand panel (SPEC 16.2): the step's component chips, then 运行设置 / 提示词 / 历史 for
 * the selected one. RunBar and pages drive it through `useInspectorStore`.
 */
export function Inspector({
  components,
  item = null,
  className,
}: {
  components: InspectorComponent[];
  /** Per-item overrides (`shot:<shot id>`, as runs read them); null = component level. */
  item?: string | null;
  className?: string;
}) {
  const { t } = useTranslation("components");
  const { t: te } = useTranslation("enums");
  const { component, tab, select, setTab } = useInspectorStore();
  const current = components.find((c) => c.id === component) ?? components[0];
  const product = useProduct(current?.productId);
  if (!current) return null;
  const name = te(`component.${current.id}` as "component.enrich", { defaultValue: current.id });
  const desc = te(`componentDesc.${current.id}` as "componentDesc.enrich", { defaultValue: "" });

  return (
    <aside
      aria-label={t("inspector.label")}
      className={cn("flex min-w-0 flex-col border-l bg-card", className)}
    >
      <div className="flex flex-col gap-2 border-b px-4 py-3">
        <div className="text-xs text-muted-foreground">{t("inspector.components")}</div>
        <div className="flex flex-wrap gap-1.5">
          {components.map((c) => (
            <Chip key={c.id} selected={c.id === current.id} onClick={() => select(c.id)}>
              {te(`component.${c.id}` as "component.enrich", { defaultValue: c.id })}
            </Chip>
          ))}
        </div>
      </div>
      <Tabs value={tab} onValueChange={(v) => setTab(v as InspectorTab)} className="gap-0">
        <TabsList aria-label={t("inspector.tabs")} className="mx-4 mt-3">
          <TabsTrigger value="run">{t("inspector.tab.run")}</TabsTrigger>
          <TabsTrigger value="prompt">{t("inspector.tab.prompt")}</TabsTrigger>
          <TabsTrigger value="history">
            {t("inspector.tab.history", { count: product.data?.versions.length ?? 0 })}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="run" className="flex flex-col gap-4 p-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-bold">{name}</h2>
            {desc ? <p className="text-sm leading-relaxed text-muted-foreground">{desc}</p> : null}
          </div>
          <ModelPicker key={`${current.id}|${item ?? ""}`} componentId={current.id} item={item} />
          {current.id === "vid" && item ? (
            <ShotWorkflow productId={current.productId} item={item} />
          ) : null}
          {product.data ? (
            <RunButtons productId={product.data.id} componentId={current.id} item={item} />
          ) : null}
          <Link
            to={paths.models()}
            className="text-sm text-primary underline-offset-4 hover:underline"
          >
            {t("inspector.globalLink")}
          </Link>
        </TabsContent>
        <TabsContent value="prompt" className="p-4">
          <ProductPane productId={current.productId} query={product}>
            {(p) => <PromptEditor product={p} componentName={name} />}
          </ProductPane>
        </TabsContent>
        <TabsContent value="history" className="p-4">
          <ProductPane productId={current.productId} query={product}>
            {(p) => <HistoryPane product={p} componentId={current.id} item={item} name={name} />}
          </ProductPane>
        </TabsContent>
      </Tabs>
    </aside>
  );
}

function ProductPane({
  productId,
  query,
  children,
}: {
  productId: string | undefined;
  query: ReturnType<typeof useProduct>;
  children: (p: NonNullable<ReturnType<typeof useProduct>["data"]>) => ReactNode;
}) {
  const { t } = useTranslation("components");
  if (!productId) return <EmptyState title={t("inspector.noProduct")} />;
  return <QueryState query={query}>{children}</QueryState>;
}

function HistoryPane({
  product,
  componentId,
  item,
  name,
}: {
  product: NonNullable<ReturnType<typeof useProduct>["data"]>;
  componentId: string;
  item: string | null;
  name: string;
}) {
  const models = useComponentModels(componentId, item);
  return <VersionHistory product={product} models={models} componentName={name} />;
}

/** 重跑 + 不满意换一个 at the bottom of 「运行设置」 (prototype Main.dc.html). */
function RunButtons({
  productId,
  componentId,
  item,
}: {
  productId: string;
  componentId: string;
  item: string | null;
}) {
  const { t } = useTranslation("components");
  const product = useProduct(productId).data;
  const models = useComponentModels(componentId, item);
  const action = useRunAction(productId);
  if (!product) return null;
  const busy = action.pending || product.running !== null;
  const est = product.estimate;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        size="lg"
        disabled={busy}
        onClick={() => action.run({ mode: product.versions.length ? "rerun" : "run" })}
      >
        <RotateCw aria-hidden />
        {t("inspector.rerun")}
      </Button>
      <ModelSwitchMenu
        options={models}
        currentKey={currentVersion(product)?.model_key}
        side="top"
        align="start"
        onPick={(model) => action.run({ mode: "switch", model })}
      >
        <Button size="lg" variant="outline" disabled={busy}>
          <ArrowLeftRight aria-hidden />
          {t("inspector.switch")}
        </Button>
      </ModelSwitchMenu>
      {est ? (
        <CostBadge where={est.where} usd={est.cost_usd} estimate seconds={est.seconds} />
      ) : null}
    </div>
  );
}
