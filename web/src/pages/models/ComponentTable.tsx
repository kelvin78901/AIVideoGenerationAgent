/**
 * Every component's run settings (prototype Models.dc.html table): location, main model,
 * fallback, alternatives; a row expands to pick models and reorder 「不满意换一个」.
 */
import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useResetOverride, useSetOverride } from "@/api/hooks/config";
import type {
  ComponentConfig,
  ComponentDef,
  PresetId,
  ResolvedConfig,
  RunLocation,
} from "@/api/schemas/config";
import type { ModelOption } from "@/api/schemas/models";
import { Chip } from "@/components/Chip";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { primaryModelKey } from "@/lib/config";
import { cn } from "@/lib/utils";
import { modelName } from "@/lib/versions";

const MODES: RunLocation[] = ["local", "api", "hybrid"];
const GRID =
  "grid grid-cols-[64px_minmax(120px,1.2fr)_176px_minmax(150px,1.6fr)_56px_minmax(140px,1.4fr)_96px_40px] items-center gap-3";

/** Models other than the ones the component runs on: fallback targets and alternatives. */
function othersOf(def: ComponentDef, v: ComponentConfig): string[] {
  if (v.mode === "off") return [];
  const used = v.mode === "hybrid" ? [v.local_model, v.api_model] : [primaryModelKey(v)];
  return [...def.local_models, ...def.api_models].filter((k) => !used.includes(k));
}

export function ComponentTable({
  defs,
  configs,
  models,
  preset,
}: {
  defs: ComponentDef[];
  /** The active preset (wording of skipped components). */
  preset: PresetId | undefined;
  /** Resolved component-level config by id; missing while loading. */
  configs: Record<string, ResolvedConfig | undefined>;
  models: ModelOption[];
}) {
  const { t } = useTranslation("models");
  // The prototype opens 视频生成 by default.
  const [open, setOpen] = useState<Record<string, boolean>>({ vid: true });
  return (
    <section aria-label={t("table.label")} className="overflow-x-auto rounded-xl border bg-card">
      <div className="min-w-[1000px]" role="table" aria-label={t("table.label")}>
        <div
          role="row"
          className={cn(GRID, "border-b px-3.5 py-2.5 text-xs font-medium text-muted-foreground")}
        >
          {(
            ["stage", "component", "location", "primary", "fallback", "fallbackTo", "alts"] as const
          ).map((k) => (
            <div key={k} role="columnheader">
              {t(`table.${k}`)}
            </div>
          ))}
          <div role="columnheader" />
        </div>
        {defs.map((def) => {
          const resolved = configs[def.id];
          return resolved ? (
            <ComponentRow
              key={def.id}
              def={def}
              resolved={resolved}
              models={models}
              preset={preset}
              open={!!open[def.id]}
              onToggle={() => setOpen((o) => ({ ...o, [def.id]: !o[def.id] }))}
            />
          ) : null;
        })}
      </div>
    </section>
  );
}

function ComponentRow({
  def,
  resolved,
  models,
  open,
  onToggle,
  preset,
}: {
  def: ComponentDef;
  resolved: ResolvedConfig;
  models: ModelOption[];
  preset: PresetId | undefined;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation("models");
  const { t: tc } = useTranslation();
  const { t: te } = useTranslation("enums");
  const { t: tn } = useTranslation("nav");
  const { t: tp } = useTranslation("components");
  const override = useSetOverride(def.id);
  const reset = useResetOverride(def.id);
  const v = resolved.values;
  const name = te(`component.${def.id}` as "component.vid");
  const label = (key: string | null) => (key ? modelName(models, key) : "");
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const set = (data: Partial<ComponentConfig>) => override.mutate(data, { onError });

  const hasApi = def.api_models.length > 0;
  const hasLocal = def.local_models.length > 0;
  const off = v.mode === "off";
  // The route's API model is no longer picked (or not on the provider's current site).
  const gone =
    !off && v.mode !== "local" && !!v.api_model && !models.some((m) => m.key === v.api_model);
  const changed = Object.values(resolved.sources).includes("component");
  const others = othersOf(def, v);
  const fbTo =
    v.fallback.to && others.includes(v.fallback.to) ? v.fallback.to : (others[0] ?? null);
  const fbOn = v.fallback.enabled && !off && !!fbTo;
  // Saved order first, then any model it does not mention yet.
  const order = [
    ...v.alt_order.filter((k) => others.includes(k)),
    ...others.filter((k) => !v.alt_order.includes(k)),
  ];
  const move = (i: number, d: -1 | 1) => {
    const next = order.slice();
    const [a, b] = [next[i], next[i + d]];
    if (a === undefined || b === undefined) return;
    next[i] = b;
    next[i + d] = a;
    set({ alt_order: next });
  };

  // 全本地 skips what has no local version; otherwise `off` is the component's own default.
  const primary = off
    ? t(preset === "local" && !hasLocal ? "table.offNoLocal" : "table.off")
    : v.mode === "hybrid"
      ? t("table.hybrid", { local: label(v.local_model), api: label(v.api_model) })
      : label(primaryModelKey(v));

  return (
    <div
      role="rowgroup"
      aria-label={name}
      className={cn("border-b border-border/60 last:border-b-0", open && "bg-muted/30")}
    >
      <div role="row" className={cn(GRID, "min-h-13 px-3.5 py-2")}>
        <div role="cell" className="text-xs text-muted-foreground">
          {tn(`steps.${def.stage}` as "steps.novel")}
        </div>
        <div role="cell" className="flex min-w-0 flex-col gap-0.5">
          <span className="text-sm font-medium">{name}</span>
          {changed ? (
            <span className="text-[11px] text-tone-warn-fg">{t("table.changed")}</span>
          ) : null}
        </div>
        <div role="cell">
          <SegmentedControl
            size="sm"
            label={t("table.locationOf", { name })}
            value={v.mode}
            onChange={(mode) => set({ mode })}
            className="grid grid-cols-3"
            options={MODES.map((m) => ({
              value: m,
              label: tp(`picker.mode.${m}`),
              disabled:
                (m === "local" && !hasLocal) ||
                (m === "api" && !hasApi) ||
                (m === "hybrid" && !(hasApi && hasLocal)),
            }))}
          />
        </div>
        <div
          role="cell"
          className={cn(
            "flex flex-col text-[13px] leading-normal",
            off && "text-tone-warn-fg",
            gone && "text-tone-fail-fg",
          )}
        >
          <span>{primary}</span>
          {gone ? <span className="text-[11px]">{t("table.gone")}</span> : null}
        </div>
        <div role="cell">
          <Switch
            checked={fbOn}
            disabled={off || !fbTo}
            aria-label={t("table.fallbackOf", { name })}
            onCheckedChange={(on) => set({ fallback: { ...v.fallback, enabled: on, to: fbTo } })}
          />
        </div>
        <div
          role="cell"
          className={cn("text-[13px]", fbOn ? "text-foreground" : "text-muted-foreground")}
        >
          {fbOn ? label(fbTo) : t("table.fallbackOff")}
        </div>
        <div role="cell" className="text-xs text-muted-foreground">
          {order.length ? t("table.altCount", { count: order.length }) : t("table.altNone")}
        </div>
        <div role="cell">
          <Button
            variant="outline"
            size="icon"
            aria-expanded={open}
            aria-label={t(open ? "table.collapse" : "table.expand", { name })}
            onClick={onToggle}
          >
            {open ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
          </Button>
        </div>
      </div>

      {open ? (
        <div className="flex flex-wrap gap-5 px-3.5 pt-1.5 pb-4.5">
          <div className="flex flex-[1_1_220px] flex-col gap-2">
            <ModelChips
              title={t("table.apiModels")}
              empty={t("table.noApi")}
              keys={def.api_models}
              selected={v.api_model}
              active={v.mode !== "local" && !off}
              label={label}
              onPick={(api_model) => set({ api_model })}
            />
            <ModelChips
              title={t("table.localModels")}
              empty={t("table.noLocal")}
              keys={def.local_models}
              selected={v.local_model}
              active={v.mode !== "api" && !off}
              label={label}
              onPick={(local_model) => set({ local_model })}
            />
          </div>
          <div className="flex flex-[1_1_200px] flex-col gap-2">
            <div className="text-xs font-medium">{t("table.fallbackTo")}</div>
            <div
              role="radiogroup"
              aria-label={t("table.fallbackTo")}
              className="flex flex-wrap gap-1.5"
            >
              {others.map((k) => (
                <Chip
                  key={k}
                  role="radio"
                  selected={fbOn && k === fbTo}
                  onClick={() => set({ fallback: { ...v.fallback, enabled: true, to: k } })}
                >
                  {label(k)}
                </Chip>
              ))}
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t("table.fallbackHint")}
            </p>
          </div>
          <div className="flex flex-[1.2_1_260px] flex-col gap-2">
            <div className="text-xs font-medium">{t("table.altOrder")}</div>
            <ol aria-label={t("table.altOrder")} className="flex flex-col gap-1.5">
              {order.map((k, i) => {
                const local = def.local_models.includes(k);
                const n = label(k);
                return (
                  <li
                    key={k}
                    className="flex min-h-9 items-center gap-2 rounded-md bg-muted/60 px-2"
                  >
                    <span className="w-4 font-mono text-xs text-muted-foreground">{i + 1}</span>
                    <StatusBadge tone={local ? "neutral" : "info"} icon={null}>
                      {t(`table.where.${local ? "local" : "api"}`)}
                    </StatusBadge>
                    <span className="flex-1 text-[13px]">{n}</span>
                    <Button
                      variant="outline"
                      size="icon"
                      className="size-8"
                      disabled={i === 0}
                      aria-label={t("table.up", { name: n })}
                      onClick={() => move(i, -1)}
                    >
                      <ChevronUp aria-hidden />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      className="size-8"
                      disabled={i === order.length - 1}
                      aria-label={t("table.down", { name: n })}
                      onClick={() => move(i, 1)}
                    >
                      <ChevronDown aria-hidden />
                    </Button>
                  </li>
                );
              })}
            </ol>
            {changed ? (
              <Button
                variant="outline"
                size="sm"
                className="self-start"
                disabled={reset.isPending}
                onClick={() =>
                  reset.mutate(undefined, {
                    onSuccess: () => toast.success(t("table.resetDone", { name })),
                    onError,
                  })
                }
              >
                {t("table.reset")}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ModelChips({
  title,
  empty,
  keys,
  selected,
  active,
  label,
  onPick,
}: {
  title: string;
  empty: string;
  keys: string[];
  selected: string | null;
  /** Whether this side is in use (local chips are idle when the component runs on the API). */
  active: boolean;
  label: (key: string) => string;
  onPick: (key: string) => void;
}) {
  return (
    <>
      <div className="mt-1 text-xs font-medium first:mt-0">{title}</div>
      <div role="radiogroup" aria-label={title} className="flex flex-wrap gap-1.5">
        {keys.map((k) => (
          <Chip key={k} role="radio" selected={active && k === selected} onClick={() => onPick(k)}>
            {label(k)}
          </Chip>
        ))}
        {keys.length === 0 ? <span className="text-xs text-muted-foreground">{empty}</span> : null}
      </div>
    </>
  );
}
