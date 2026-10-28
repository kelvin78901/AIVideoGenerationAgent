/** 模型与兜底 · 全局默认 (prototype Models.dc.html; SPEC 7), plus 按镜头选工作流 (SPEC 6.4.8) and 工作流库 (SPEC 6.4.6), neither in the prototype. */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import {
  useComponentCatalog,
  useConfigDefaults,
  useProviders,
  useResolvedConfigs,
  useSetConfigDefaults,
} from "@/api/hooks/config";
import { useRouteEpisode, useUpdateEpisode } from "@/api/hooks/series";
import { useMachineProfile } from "@/api/hooks/setup";
import { PresetIdSchema, type ConfigDefaults } from "@/api/schemas/config";
import { paths } from "@/app/paths";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Input, Label } from "@/components/ui/form";
import { formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ComponentTable } from "@/pages/models/ComponentTable";
import { KeyDialog } from "@/pages/models/KeyDialog";
import { WorkflowLibrary } from "@/pages/models/WorkflowLibrary";
import { WorkflowRules } from "@/pages/models/WorkflowRules";

const PRESETS = PresetIdSchema.options;

export default function ModelsPage() {
  const { t } = useTranslation("models");
  const catalog = useComponentCatalog();
  const defs = catalog.data?.components ?? [];
  const resolved = useResolvedConfigs(defs.map((d) => d.id));
  const configs = Object.fromEntries(defs.map((d, i) => [d.id, resolved[i]?.data]));
  const defaults = useConfigDefaults();

  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-5 px-7 pt-6 pb-12">
      <PageHeader title={t("title")} lead={t("lead")} />
      <Presets />
      <div className="flex flex-wrap gap-4">
        <Services localOk={catalog.data?.local_runtime_ok} />
        <FallbackPolicy />
      </div>
      <QueryState query={catalog} skeleton={<Skeleton className="h-96 w-full" />}>
        {(data) => (
          <ComponentTable
            defs={data.components}
            configs={configs}
            models={data.models}
            preset={defaults.data?.preset}
          />
        )}
      </QueryState>
      <WorkflowRules models={catalog.data?.models ?? []} />
      <WorkflowLibrary />
    </div>
  );
}

function Presets() {
  const { t } = useTranslation("models");
  const { t: tc } = useTranslation();
  const defaults = useConfigDefaults();
  const setDefaults = useSetConfigDefaults();
  const active = defaults.data?.preset;
  return (
    <section aria-labelledby="presets-title" className="flex flex-col gap-2.5">
      <h2 id="presets-title" className="text-base font-bold">
        {t("presets.title")}
      </h2>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        {PRESETS.map((id) => {
          const on = active === id;
          return (
            <button
              key={id}
              type="button"
              aria-pressed={on}
              disabled={!defaults.data || setDefaults.isPending}
              onClick={() =>
                setDefaults.mutate(
                  { preset: id },
                  {
                    onSuccess: () =>
                      toast.success(t("presets.switched", { name: t(`presets.name.${id}`) })),
                    onError: (err) => toast.error(errorMessage(tc, err)),
                  },
                )
              }
              className={cn(
                "flex flex-col gap-1.5 rounded-lg border-2 bg-card p-3.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default",
                on ? "border-primary" : "border-border hover:border-muted-foreground/40",
              )}
            >
              <span className="flex items-center gap-2">
                <span className="text-base font-bold">{t(`presets.name.${id}`)}</span>
                {on ? (
                  <span className="rounded bg-primary px-1.5 py-0.5 text-[11px] text-primary-foreground">
                    {t("presets.current")}
                  </span>
                ) : null}
              </span>
              <span className="text-[13px] leading-relaxed text-muted-foreground">
                {t(`presets.desc.${id}`)}
              </span>
              <span className="text-xs font-medium">{t(`presets.cost.${id}`)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function Services({ localOk }: { localOk: boolean | undefined }) {
  const { t } = useTranslation("models");
  const profile = useMachineProfile();
  const providers = useProviders();
  const [openId, setOpenId] = useState<string | null>(null);
  const gpu = profile.data?.machine.gpu;
  // Unknown (still loading or failed) is never shown as connected / no GPU.
  const conn = t(
    localOk === undefined
      ? "services.statusUnknown"
      : localOk
        ? "services.connected"
        : "services.disconnected",
  );
  const list = (providers.data?.providers ?? []).filter((p) => p.needs_key);
  const open = list.find((p) => p.id === openId) ?? null;

  return (
    <section
      aria-labelledby="services-title"
      className="flex min-w-0 flex-[1.4_1_420px] flex-col gap-2.5 rounded-xl border bg-card p-4"
    >
      <h2 id="services-title" className="text-base font-bold">
        {t("services.title")}
      </h2>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] leading-relaxed">
        <span>
          {t("services.local", {
            gpu: gpu
              ? `${gpu.name} ${gpu.vram_gb}GB`
              : t(profile.data ? "services.noGpu" : "services.statusUnknown"),
            comfy: conn,
            llm: conn,
          })}
        </span>
        <Link to={paths.setup()} className="text-primary underline-offset-4 hover:underline">
          {t("services.rescan")}
        </Link>
      </div>
      <QueryState query={providers} skeleton={<Skeleton className="h-8 w-full" />}>
        {() => (
          <div className="flex flex-wrap gap-1.5">
            {list.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setOpenId(p.id)}
                className={cn(
                  "min-h-8 rounded-md border px-2.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  p.has_key
                    ? "bg-card hover:bg-accent/60"
                    : "border-tone-warn-border bg-tone-warn-bg text-tone-warn-fg",
                )}
              >
                {t("services.chip", {
                  name: p.name,
                  state: t(p.has_key ? "services.keySet" : "services.keyMissing"),
                })}
              </button>
            ))}
          </div>
        )}
      </QueryState>
      <p className="text-xs leading-relaxed text-muted-foreground">{t("services.note")}</p>
      <p className="text-xs leading-relaxed text-muted-foreground">{t("services.mediaLater")}</p>
      <KeyDialog provider={open} onOpenChange={(o) => !o && setOpenId(null)} />
    </section>
  );
}

function FallbackPolicy() {
  const { t } = useTranslation("models");
  const { t: tc } = useTranslation();
  const defaults = useConfigDefaults();
  const setDefaults = useSetConfigDefaults();
  const { episode } = useRouteEpisode();
  const update = useUpdateEpisode(episode?.id);
  const [budget, setBudget] = useState<string | null>(null);
  const shown = budget ?? episode?.budget_usd?.toString() ?? "";
  const notify = defaults.data?.fallback_notify ?? "after";
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));

  const saveBudget = () => {
    if (budget === null) return;
    const n = budget.trim() === "" ? null : Number(budget);
    if (n !== null && (!Number.isFinite(n) || n < 0)) {
      toast.warning(t("fallback.budgetInvalid"));
      setBudget(null);
      return;
    }
    if (n === (episode?.budget_usd ?? null)) {
      setBudget(null);
      return;
    }
    update.mutate(
      { budget_usd: n },
      {
        onSuccess: () => {
          setBudget(null);
          toast.success(t("fallback.budgetSaved", { amount: n === null ? "—" : formatUsd(n) }));
        },
        onError,
      },
    );
  };

  return (
    <section
      aria-labelledby="fallback-title"
      className="flex min-w-0 flex-[1_1_320px] flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <h2 id="fallback-title" className="text-base font-bold">
        {t("fallback.title")}
      </h2>
      <SegmentedControl<ConfigDefaults["fallback_notify"]>
        label={t("fallback.mode")}
        value={notify}
        onChange={(fallback_notify) => setDefaults.mutate({ fallback_notify }, { onError })}
        className="grid grid-cols-2"
        options={(["after", "ask"] as const).map((m) => ({ value: m, label: t(`fallback.${m}`) }))}
      />
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t(`fallback.hint.${notify}`)}
      </p>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Label htmlFor="ep-budget">{t("fallback.budget")}</Label>
        <Input
          id="ep-budget"
          type="number"
          min={0}
          step={1}
          value={shown}
          disabled={!episode}
          onChange={(e) => setBudget(e.target.value)}
          onBlur={saveBudget}
          onKeyDown={(e) => {
            if (e.key === "Enter") saveBudget();
          }}
          className="w-22"
        />
        <span className="text-xs text-muted-foreground">{t("fallback.budgetNote")}</span>
      </div>
    </section>
  );
}
