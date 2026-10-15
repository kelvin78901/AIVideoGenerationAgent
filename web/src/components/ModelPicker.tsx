import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import {
  useComponentCatalog,
  useMissingKeys,
  useResolvedConfig,
  useSetOverride,
} from "@/api/hooks/config";
import type { Message } from "@/api/schemas/common";
import {
  FallbackTriggerSchema,
  type ComponentConfig,
  type ConfigField,
  type ConfigSource,
  type RunLocation,
} from "@/api/schemas/config";
import type { ModelOption } from "@/api/schemas/models";
import { Chip } from "@/components/Chip";
import { CostBadge } from "@/components/CostBadge";
import { QueryState, Skeleton } from "@/components/QueryState";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StatusBadge } from "@/components/StatusBadge";
import { Input, Label } from "@/components/ui/form";
import { RadioCard, RadioGroup } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { modelName } from "@/lib/versions";
import { cn } from "@/lib/utils";

/** API services shown before 「更多供应商」 (prototype: the first 6). */
const API_VISIBLE = 6;
const MODES: RunLocation[] = ["local", "api", "hybrid"];

type Role = "main" | "final" | "draft" | "fallback" | "unused" | "none";

function roleOf(has: boolean, mode: RunLocation, side: "api" | "local", fallback: boolean): Role {
  if (!has) return "none";
  if (mode === side) return "main";
  if (mode === "hybrid") return side === "api" ? "final" : "draft";
  return fallback ? "fallback" : "unused";
}

/** Small tag saying which config level a value comes from (SPEC 7.1). */
function SourceTag({ source }: { source: ConfigSource | undefined }) {
  const { t } = useTranslation("components");
  if (!source) return null;
  const label = t(`picker.source.${source}`);
  return (
    <span
      data-testid="config-source"
      title={t("picker.sourceTitle", { source: label })}
      className={cn(
        "rounded border px-1 text-[11px] leading-4 text-muted-foreground",
        source !== "preset" && "border-tone-info-border text-tone-info-fg",
      )}
    >
      {label}
    </span>
  );
}

function FieldHead({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <div className="text-sm font-medium">{children}</div>
      <div className="ml-auto flex items-center gap-1.5">{aside}</div>
    </div>
  );
}

function RoleBadge({ role }: { role: Role }) {
  const { t } = useTranslation("components");
  const active = role === "main" || role === "final" || role === "draft";
  return (
    <StatusBadge tone={active ? "info" : "neutral"} icon={null}>
      {t(`picker.role.${role}`)}
    </StatusBadge>
  );
}

function ModelRadios({
  label,
  models,
  value,
  onChange,
  missingKeys,
}: {
  label: string;
  models: ModelOption[];
  value: string | null;
  onChange: (key: string) => void;
  missingKeys: ReadonlySet<string>;
}) {
  const { t } = useTranslation("components");
  return (
    <RadioGroup aria-label={label} value={value ?? ""} onValueChange={onChange} className="gap-1.5">
      {models.map((m) => (
        <RadioCard key={m.key} value={m.key}>
          <span className="flex items-center gap-2">
            <span className="text-sm">{m.display}</span>
            {missingKeys.has(m.key) ? (
              <StatusBadge tone="warn">{t("picker.keyMissing")}</StatusBadge>
            ) : null}
          </span>
          <CostBadge where={m.where} price={m.price} className="block" />
        </RadioCard>
      ))}
    </RadioGroup>
  );
}

/**
 * 「运行设置」 (SPEC 16.2): run location, API service, local model, automatic fallback and the
 * per-call cap of one component, optionally for one item (`shot:1-05`). Every change is an
 * override at that level; each field shows the level its value comes from.
 */
export function ModelPicker({
  componentId,
  item = null,
}: {
  componentId: string;
  item?: string | null;
}) {
  const catalog = useComponentCatalog();
  const resolved = useResolvedConfig(componentId, item);
  return (
    <QueryState query={catalog} skeleton={<Skeleton className="h-96 w-full" />}>
      {(cat) => (
        <QueryState query={resolved} skeleton={<Skeleton className="h-96 w-full" />}>
          {(cfg) => {
            const def = cat.components.find((c) => c.id === componentId);
            const byKey = (keys: string[]) =>
              keys.flatMap((k) => cat.models.find((m) => m.key === k) ?? []);
            return (
              <PickerForm
                componentId={componentId}
                item={item}
                values={cfg.values}
                sources={cfg.sources}
                apiModels={byKey(def?.api_models ?? [])}
                localModels={byKey(def?.local_models ?? [])}
                unavailable={def?.unavailable ?? {}}
                runtimeOk={cat.local_runtime_ok}
                isLlm={def?.kind === "llm"}
              />
            );
          }}
        </QueryState>
      )}
    </QueryState>
  );
}

function PickerForm({
  componentId,
  item,
  values,
  sources,
  apiModels,
  localModels,
  unavailable,
  runtimeOk,
  isLlm,
}: {
  componentId: string;
  item: string | null;
  values: ComponentConfig;
  sources: Partial<Record<ConfigField, ConfigSource>>;
  apiModels: ModelOption[];
  localModels: ModelOption[];
  unavailable: Partial<Record<RunLocation, Message>>;
  runtimeOk: boolean;
  isLlm: boolean;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const override = useSetOverride(componentId, item);
  const missingKeys = useMissingKeys();
  const selectedApi = apiModels.findIndex((m) => m.key === values.api_model);
  const [showAll, setShowAll] = useState(selectedApi >= API_VISIBLE);
  const [cap, setCap] = useState(values.per_call_cap_usd?.toString() ?? "");

  const set = (data: Partial<ComponentConfig>) =>
    override.mutate(data, { onError: (err) => toast.error(errorMessage(tc, err)) });

  const hasApi = apiModels.length > 0;
  const hasLocal = localModels.length > 0;
  const reason = (mode: RunLocation): string | undefined => {
    const r =
      unavailable[mode] ??
      (mode === "local" && !hasLocal ? { code: "no_local_model", params: {} } : undefined) ??
      (mode === "api" && !hasApi ? { code: "no_api_model", params: {} } : undefined) ??
      (mode === "hybrid" && !(hasApi && hasLocal) ? { code: "needs_both", params: {} } : undefined);
    return r
      ? t(`picker.unavailable.${r.code}` as "picker.unavailable.machine", r.params)
      : undefined;
  };
  const reasons = MODES.flatMap((m) => {
    const r = reason(m);
    return r ? [{ mode: m, text: r }] : [];
  });

  const all = [...localModels, ...apiModels];
  const primary =
    values.mode === "api" ? values.api_model : (values.local_model ?? values.api_model);
  const others = all.filter((m) => m.key !== primary);
  const fb = values.fallback;
  const target = fb.to && fb.to !== primary ? modelName(all, fb.to) : t("picker.fallbackNext");
  const visibleApi = showAll ? apiModels : apiModels.slice(0, API_VISIBLE);

  const saveCap = () => {
    const n = cap.trim() === "" ? null : Number(cap);
    if (n !== null && (!Number.isFinite(n) || n < 0)) {
      setCap(values.per_call_cap_usd?.toString() ?? "");
      return;
    }
    if (n !== values.per_call_cap_usd) set({ per_call_cap_usd: n });
  };

  return (
    <div className="flex flex-col gap-5" aria-busy={override.isPending || undefined}>
      <section className="flex flex-col gap-2">
        <FieldHead aside={<SourceTag source={sources.mode} />}>{t("picker.location")}</FieldHead>
        <SegmentedControl
          label={t("picker.location")}
          value={values.mode}
          onChange={(mode) => set({ mode })}
          options={MODES.map((m) => ({
            value: m,
            label: t(`picker.mode.${m}`),
            disabled: !!reason(m),
            hint: reason(m),
          }))}
        />
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t(`picker.modeHint.${values.mode}`)}
        </p>
        {reasons.length > 0 ? (
          <ul className="text-xs text-muted-foreground">
            {reasons.map((r) => (
              <li key={r.mode}>
                {t("picker.reasonLine", { mode: t(`picker.mode.${r.mode}`), reason: r.text })}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="flex flex-col gap-2">
        <FieldHead
          aside={
            <>
              <SourceTag source={sources.api_model} />
              <RoleBadge role={roleOf(hasApi, values.mode, "api", fb.enabled)} />
            </>
          }
        >
          {t("picker.api")}
        </FieldHead>
        {hasApi ? (
          <>
            <ModelRadios
              label={t("picker.api")}
              models={visibleApi}
              value={values.api_model}
              onChange={(api_model) => set({ api_model })}
              missingKeys={missingKeys}
            />
            {apiModels.length > API_VISIBLE ? (
              <Button
                variant="link"
                className="h-auto self-start p-0 text-xs"
                aria-expanded={showAll}
                onClick={() => setShowAll(!showAll)}
              >
                {showAll
                  ? t("picker.less")
                  : t("picker.more", { count: apiModels.length - API_VISIBLE })}
              </Button>
            ) : null}
            {isLlm ? (
              <p className="text-xs text-muted-foreground">{t("picker.priceNote")}</p>
            ) : null}
          </>
        ) : (
          <p className="text-xs text-muted-foreground">{t("picker.noApi")}</p>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <FieldHead
          aside={
            <>
              <SourceTag source={sources.local_model} />
              <RoleBadge role={roleOf(hasLocal, values.mode, "local", fb.enabled)} />
            </>
          }
        >
          {t("picker.local")}
        </FieldHead>
        {hasLocal ? (
          <>
            <ModelRadios
              label={t("picker.local")}
              models={localModels}
              value={values.local_model}
              onChange={(local_model) => set({ local_model })}
              missingKeys={missingKeys}
            />
            <p className={cn("text-xs", runtimeOk ? "text-muted-foreground" : "text-tone-warn-fg")}>
              {t(runtimeOk ? "picker.runtimeOk" : "picker.runtimeDown")}
            </p>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">{t("picker.noLocal")}</p>
        )}
      </section>

      <section className="flex flex-col gap-2.5 rounded-md border p-3">
        <div className="flex items-start gap-3">
          <Label htmlFor={`fb-${componentId}`} className="flex-1 flex-col items-start gap-1">
            <span className="flex items-center gap-1.5">
              {t("picker.fallback")}
              <SourceTag source={sources.fallback} />
            </span>
            <span className="text-xs leading-relaxed font-normal text-muted-foreground">
              {fb.enabled
                ? t("picker.fallbackOn", { primary: modelName(all, primary), target })
                : t("picker.fallbackOff")}
            </span>
          </Label>
          <Switch
            id={`fb-${componentId}`}
            checked={fb.enabled}
            onCheckedChange={(enabled) => set({ fallback: { ...fb, enabled } })}
          />
        </div>
        {fb.enabled ? (
          <>
            <div className="text-xs font-medium">{t("picker.when")}</div>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("picker.when")}>
              {FallbackTriggerSchema.options.map((trigger) => {
                const on = fb.on.includes(trigger);
                return (
                  <Chip
                    key={trigger}
                    check
                    selected={on}
                    onClick={() =>
                      set({
                        fallback: {
                          ...fb,
                          on: on ? fb.on.filter((x) => x !== trigger) : [...fb.on, trigger],
                        },
                      })
                    }
                  >
                    {t(`picker.trigger.${trigger}`, {
                      minutes: Math.round(fb.timeout_s / 60),
                      n: fb.qa_fail_n,
                    })}
                  </Chip>
                );
              })}
            </div>
            <div className="text-xs font-medium">{t("picker.target")}</div>
            <div
              className="flex flex-wrap gap-1.5"
              role="radiogroup"
              aria-label={t("picker.target")}
            >
              {others.map((m) => (
                <Chip
                  key={m.key}
                  role="radio"
                  selected={m.key === fb.to}
                  onClick={() => set({ fallback: { ...fb, to: m.key } })}
                >
                  {m.display}
                </Chip>
              ))}
            </div>
          </>
        ) : null}
      </section>

      <section className="flex flex-col gap-1.5">
        <FieldHead aside={<SourceTag source={sources.per_call_cap_usd} />}>
          <Label htmlFor={`cap-${componentId}`}>{t("picker.cap")}</Label>
        </FieldHead>
        <Input
          id={`cap-${componentId}`}
          type="number"
          min={0}
          step={0.1}
          value={cap}
          onChange={(e) => setCap(e.target.value)}
          onBlur={saveCap}
          onKeyDown={(e) => {
            if (e.key === "Enter") saveCap();
          }}
        />
        <p className="text-xs text-muted-foreground">{t("picker.capHint")}</p>
      </section>
    </div>
  );
}
