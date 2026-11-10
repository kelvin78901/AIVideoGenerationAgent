/**
 * 按镜头选工作流 (SPEC 6.4.8; not in the prototype, M0.5 style): the series' rules table for
 * the video component's local workflows, top to bottom, and the LLM suggestion switch. Every
 * change saves the whole table (`PUT /series/{id}/workflow-rules`).
 */
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useResolvedConfig } from "@/api/hooks/config";
import { useSaveWorkflowRules, useWorkflowRules } from "@/api/hooks/generate";
import { useSeries, useSeriesId } from "@/api/hooks/series";
import {
  SELECT_CONDITIONS,
  SelectWhenSchema,
  type SelectWhen,
  type WorkflowRule,
  type WorkflowRules as Rules,
} from "@/api/schemas/generate";
import type { ModelOption } from "@/api/schemas/models";
import { QueryState, Skeleton } from "@/components/QueryState";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { modelName } from "@/lib/versions";
import { WORKFLOW_RULES_ANCHOR } from "@/lib/workflowRules";

const VIDEO = "vid";
const SELECT =
  "h-8 w-full min-w-0 rounded-md border bg-card px-2 text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

type Cond = (typeof SELECT_CONDITIONS)[number];
const ENUM_CONDS = {
  framing: { ns: "framing", values: SelectWhenSchema.shape.framing.unwrap().options },
  shot_type: { ns: "shotType", values: SelectWhenSchema.shape.shot_type.unwrap().options },
  audio_mode: { ns: "audioMode", values: SelectWhenSchema.shape.audio_mode.unwrap().options },
} as const;

/** The value a condition's select shows: "" = any. */
function condValue(when: SelectWhen, cond: Cond): string {
  const v = when[cond];
  return v === undefined ? "" : String(v);
}

function withCond(when: SelectWhen, cond: Cond, raw: string): SelectWhen {
  const value = raw === "" ? undefined : cond in ENUM_CONDS ? raw : raw === "true";
  const next = Object.entries({ ...when, [cond]: value }).filter(([, v]) => v !== undefined);
  return SelectWhenSchema.parse(Object.fromEntries(next));
}

export function WorkflowRules({ models }: { models: readonly ModelOption[] }) {
  const seriesId = useSeriesId();
  const rules = useWorkflowRules(seriesId);
  const ref = useRef<HTMLElement>(null);
  const { hash } = useLocation();
  useEffect(() => {
    if (hash === `#${WORKFLOW_RULES_ANCHOR}` && rules.data) {
      ref.current?.scrollIntoView({ block: "start" });
    }
  }, [hash, rules.data]);

  return (
    <section
      ref={ref}
      id={WORKFLOW_RULES_ANCHOR}
      aria-labelledby="wf-rules-title"
      className="flex scroll-mt-4 flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <QueryState query={rules} skeleton={<Skeleton className="h-40 w-full" />}>
        {(data) => <RulesTable seriesId={seriesId} rules={data} models={models} />}
      </QueryState>
    </section>
  );
}

function RulesTable({
  seriesId,
  rules,
  models,
}: {
  seriesId: string;
  rules: Rules;
  models: readonly ModelOption[];
}) {
  const { t } = useTranslation("models");
  const { t: tc } = useTranslation();
  const series = useSeries(seriesId).data;
  const fallback = useResolvedConfig(VIDEO).data?.values.local_model ?? null;
  const save = useSaveWorkflowRules(seriesId);
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const put = (next: Partial<Pick<Rules, "rules" | "suggest">>) =>
    save.mutate({ rules: rules.rules, suggest: rules.suggest, ...next }, { onError });
  const setRule = (i: number, rule: WorkflowRule) =>
    put({ rules: rules.rules.map((r, j) => (j === i ? rule : r)) });
  const move = (i: number, by: -1 | 1) => {
    const next = [...rules.rules];
    const [rule] = next.splice(i, 1);
    if (rule) next.splice(i + by, 0, rule);
    put({ rules: next });
  };
  const choices = [
    ...rules.models,
    ...rules.rules.map((r) => r.model).filter((m) => !rules.models.includes(m)),
  ];
  const fallbackName = modelName(models, fallback) || "—";
  const busy = save.isPending;

  return (
    <>
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-[1_1_480px] flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="wf-rules-title" className="text-base font-bold">
              {t("wfRules.title")}
            </h2>
            <StatusBadge tone={rules.saved ? "info" : "neutral"} icon={null}>
              {t(rules.saved ? "wfRules.saved" : "wfRules.defaults")}
            </StatusBadge>
          </div>
          <p className="text-[13px] leading-relaxed text-muted-foreground">
            {t("wfRules.lead", { fallback: fallbackName, series: series?.title ?? seriesId })}
          </p>
        </div>
        <div className="flex gap-2">
          {rules.saved ? (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                save.mutate(null, {
                  onSuccess: () => toast.success(t("wfRules.resetDone")),
                  onError,
                })
              }
            >
              {t("wfRules.reset")}
            </Button>
          ) : null}
          <Button
            disabled={busy || !rules.models.length}
            onClick={() =>
              put({ rules: [...rules.rules, { when: {}, model: rules.models[0] ?? "" }] })
            }
          >
            <Plus aria-hidden />
            {t("wfRules.add")}
          </Button>
        </div>
      </div>
      {rules.rules.length ? (
        <ol aria-label={t("wfRules.title")} className="flex flex-col gap-2">
          {rules.rules.map((rule, i) => (
            <RuleRow
              key={i}
              n={i + 1}
              rule={rule}
              last={i === rules.rules.length - 1}
              choices={choices}
              models={models}
              disabled={busy}
              onChange={(r) => setRule(i, r)}
              onMove={(by) => move(i, by)}
              onRemove={() => put({ rules: rules.rules.filter((_, j) => j !== i) })}
            />
          ))}
        </ol>
      ) : (
        <p className="rounded-lg border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
          {t("wfRules.empty", { fallback: fallbackName })}
        </p>
      )}
      <div className="flex items-start gap-3 border-t pt-3">
        <Switch
          id="wf-suggest"
          checked={rules.suggest}
          disabled={busy}
          onCheckedChange={(suggest) => put({ suggest })}
          className="mt-0.5"
        />
        <div className="flex min-w-0 flex-col gap-0.5">
          <label htmlFor="wf-suggest" className="text-sm font-medium">
            {t("wfRules.suggest")}
          </label>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t("wfRules.suggestHint")}
          </p>
        </div>
      </div>
    </>
  );
}

function RuleRow({
  n,
  rule,
  last,
  choices,
  models,
  disabled,
  onChange,
  onMove,
  onRemove,
}: {
  n: number;
  rule: WorkflowRule;
  last: boolean;
  choices: readonly string[];
  models: readonly ModelOption[];
  disabled: boolean;
  onChange: (rule: WorkflowRule) => void;
  onMove: (by: -1 | 1) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation("models");
  const { t: te } = useTranslation("enums");
  const options = (cond: Cond): [string, string][] => {
    if (cond === "framing" || cond === "shot_type" || cond === "audio_mode") {
      const { ns, values } = ENUM_CONDS[cond];
      return values.map((v) => [v, te(`${ns}.${v}` as "framing.wide")]);
    }
    return [
      ["true", t("wfRules.yes")],
      ["false", t("wfRules.no")],
    ];
  };

  return (
    <li className="flex flex-wrap items-end gap-x-3 gap-y-2 rounded-lg border bg-background/40 px-3 py-2.5">
      <span className="w-14 shrink-0 pb-1.5 text-xs font-semibold text-muted-foreground">
        {t("wfRules.rule", { n })}
      </span>
      <div className="grid min-w-0 flex-[1_1_620px] grid-cols-[repeat(auto-fit,minmax(96px,1fr))] gap-2">
        {SELECT_CONDITIONS.map((cond) => (
          <label key={cond} className="flex min-w-0 flex-col gap-1 text-xs text-muted-foreground">
            {t(`wfRules.cond.${cond}`)}
            <select
              aria-label={t("wfRules.condOf", { n, cond: t(`wfRules.cond.${cond}`) })}
              className={SELECT}
              disabled={disabled}
              value={condValue(rule.when, cond)}
              onChange={(e) =>
                onChange({ ...rule, when: withCond(rule.when, cond, e.target.value) })
              }
            >
              <option value="">{t("wfRules.any")}</option>
              {options(cond).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <span className="pb-1.5 text-sm text-muted-foreground">{t("wfRules.then")}</span>
      <select
        aria-label={t("wfRules.modelOf", { n })}
        className={`${SELECT} w-auto min-w-44 flex-[0_1_220px] font-medium text-foreground`}
        disabled={disabled}
        value={rule.model}
        onChange={(e) => onChange({ ...rule, model: e.target.value })}
      >
        {choices.map((key) => (
          <option key={key} value={key}>
            {modelName(models, key)}
          </option>
        ))}
      </select>
      <div className="flex gap-1">
        <Button
          size="icon"
          variant="ghost"
          aria-label={t("wfRules.up", { n })}
          disabled={disabled || n === 1}
          onClick={() => onMove(-1)}
        >
          <ArrowUp aria-hidden />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          aria-label={t("wfRules.down", { n })}
          disabled={disabled || last}
          onClick={() => onMove(1)}
        >
          <ArrowDown aria-hidden />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          aria-label={t("wfRules.remove", { n })}
          disabled={disabled}
          onClick={onRemove}
        >
          <Trash2 aria-hidden />
        </Button>
      </div>
    </li>
  );
}
