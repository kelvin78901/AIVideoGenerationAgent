/**
 * 这个镜头的工作流 (SPEC 6.4.8; not in the prototype, M0.5 style), under the video
 * component's ModelPicker in the Inspector: which workflow the current take went to and why
 * (its `params.select`), the one the next take goes to, and that workflow's branches
 * switched for this shot.
 */
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useComponentCatalog, useResolvedConfig, useSetOverride } from "@/api/hooks/config";
import { useProduct } from "@/api/hooks/products";
import { useWorkflows } from "@/api/hooks/workflows";
import { TakeSelectSchema, type TakeSelect } from "@/api/schemas/generate";
import type { ModelOption } from "@/api/schemas/models";
import type { Product } from "@/api/schemas/products";
import type { Workflow } from "@/api/schemas/workflows";
import { paths } from "@/app/paths";
import { StatusBadge } from "@/components/StatusBadge";
import { Switch } from "@/components/ui/switch";
import { currentVersion, modelName } from "@/lib/versions";
import { describeWhen, WORKFLOW_RULES_ANCHOR } from "@/lib/workflowRules";

const VIDEO = "vid";

/** The take whose workflow choice to show: the current one if made here, else the local
 * draft an API final was made from, else the newest local take. */
function localTake(product: Product) {
  const v = currentVersion(product);
  if (!v || v.where === "local") return v;
  const parent = product.versions.find((p) => p.id === v.parent_version_id);
  if (parent?.where === "local") return parent;
  return product.versions.findLast((p) => p.where === "local") ?? v;
}

export function ShotWorkflow({ productId, item }: { productId?: string; item: string }) {
  const { t } = useTranslation("components");
  const product = useProduct(productId).data;
  const models = useComponentCatalog().data?.models ?? [];
  const cfg = useResolvedConfig(VIDEO, item).data;
  const workflows = useWorkflows().data ?? [];
  // The workflow the next take goes to: the estimate has applied the rules table already.
  const est = product?.estimate;
  const next = est?.where === "local" ? est.model_key : (cfg?.values.local_model ?? null);
  const workflow = workflows.find((w) => w.model_key === next);

  return (
    <section
      aria-labelledby="shot-workflow-title"
      className="flex flex-col gap-2.5 rounded-lg border bg-background/40 p-3"
    >
      <h3 id="shot-workflow-title" className="text-sm font-bold">
        {t("inspector.workflow.title")}
      </h3>
      <Why product={product} models={models} />
      {next ? (
        <p className="text-[13px]">
          {t("inspector.workflow.next", { model: modelName(models, next) })}
        </p>
      ) : null}
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("inspector.workflow.change")}{" "}
        <Link
          to={`${paths.models()}#${WORKFLOW_RULES_ANCHOR}`}
          className="text-primary underline-offset-4 hover:underline"
        >
          {t("inspector.workflow.rulesLink")}
        </Link>
      </p>
      {cfg && next ? (
        <Branches
          item={item}
          workflow={workflow}
          name={modelName(models, next)}
          states={cfg.values.branches ?? {}}
        />
      ) : null}
    </section>
  );
}

function Why({ product, models }: { product?: Product; models: readonly ModelOption[] }) {
  const { t } = useTranslation("components");
  const { t: tm } = useTranslation("models");
  const { t: te } = useTranslation("enums");
  const take = product ? localTake(product) : undefined;
  if (!take) return <p className="text-sm">{t("inspector.workflow.none")}</p>;
  if (take.where !== "local") return <p className="text-sm">{t("inspector.workflow.api")}</p>;
  const parsed = TakeSelectSchema.safeParse(take.params.select);
  const select: TakeSelect | null = parsed.success ? parsed.data : null;
  const n = (select?.rule ?? 0) + 1;
  const detail = !select
    ? null
    : select.by === "rule"
      ? t("inspector.workflow.rule", { n, when: describeWhen(tm, te, select.when ?? {}) })
      : select.by === "suggest"
        ? t("inspector.workflow.suggest", {
            model: modelName(models, select.suggested_by) || "LLM",
            reason: select.reason ?? "",
          })
        : t(`inspector.workflow.${select.by}`);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">
          {t("inspector.workflow.of", { n: take.n, model: modelName(models, take.model_key) })}
        </span>
        {select ? (
          <StatusBadge tone={select.by === "default" ? "neutral" : "info"} icon={null}>
            {t(`inspector.workflow.by.${select.by}`, { n })}
          </StatusBadge>
        ) : null}
      </div>
      {detail ? (
        <p className="text-[13px] leading-relaxed text-muted-foreground">{detail}</p>
      ) : null}
    </div>
  );
}

function Branches({
  item,
  workflow,
  name,
  states,
}: {
  item: string;
  workflow: Workflow | undefined;
  name: string;
  states: Record<string, boolean | null>;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const override = useSetOverride(VIDEO, item);
  const branches = workflow?.branches ?? [];
  const set = (id: string, on: boolean | null) =>
    override.mutate(
      { branches: { [id]: on } },
      { onError: (err) => toast.error(errorMessage(tc, err)) },
    );

  return (
    <div className="flex flex-col gap-1.5 border-t pt-2.5">
      <h4 className="text-xs font-semibold text-muted-foreground">
        {t("inspector.workflow.branches")}
      </h4>
      {branches.length ? (
        <ul className="flex flex-col gap-2">
          {branches.map((b) => {
            const chosen = states[b.id];
            const on = chosen ?? b.default;
            return (
              <li key={b.id} className="flex flex-wrap items-center gap-2 text-sm">
                <Switch
                  checked={on}
                  disabled={override.isPending}
                  aria-label={t("inspector.workflow.branchOf", { name: b.name })}
                  onCheckedChange={(next) => set(b.id, next === b.default ? null : next)}
                />
                <span className="font-medium">{b.name}</span>
                <span className="text-xs text-muted-foreground">
                  {t(`inspector.workflow.kind.${b.kind}`)} ·{" "}
                  {t(
                    b.default ? "inspector.workflow.default_on" : "inspector.workflow.default_off",
                  )}
                </span>
                {b.trial === null ? (
                  <StatusBadge tone="warn">{t("inspector.workflow.untested")}</StatusBadge>
                ) : null}
                {chosen !== undefined && chosen !== null ? (
                  <button
                    type="button"
                    className="text-xs text-primary underline-offset-4 hover:underline"
                    onClick={() => set(b.id, null)}
                  >
                    {t("inspector.workflow.branchReset")}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">
          {t("inspector.workflow.noBranches", { model: name })}
        </p>
      )}
    </div>
  );
}
