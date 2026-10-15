/** 首次启动 · 主机检测与自动安装 (prototype Setup.dc.html; SPEC 12). */
import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { onEvent } from "@/api/events";
import {
  useDemoMachine,
  useInstall,
  useMachineProfile,
  useRetrySetupItem,
  useScan,
  useSkipSetupItem,
} from "@/api/hooks/setup";
import {
  SetupLogSchema,
  type MachineProfile,
  type Mirror,
  type SetupLog,
  type SetupPhase,
} from "@/api/schemas/setup";
import { DEMO_DATA } from "@/app/demo";
import { DEMO_EPISODE, DEMO_SERIES, paths } from "@/app/paths";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/form";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { ItemGroups } from "@/pages/setup/ItemGroups";
import { InstallLog } from "@/pages/setup/InstallLog";
import {
  GROUPS,
  installableIds,
  overallPct,
  requiredIds,
  statusCounts,
  statusTone,
  useItemName,
} from "@/pages/setup/items";

const MIRRORS: Mirror[] = ["auto", "official", "cn"];
const STEP_KEYS = ["scan", "install", "done"] as const;

const stepOf = (phase: SetupPhase) => (phase === "installing" ? 1 : phase === "done" ? 2 : 0);

function Steps({ phase }: { phase: SetupPhase }) {
  const { t } = useTranslation("setup");
  const current = stepOf(phase);
  return (
    <ol aria-label={t("steps.label")} className="flex flex-wrap gap-2">
      {STEP_KEYS.map((key, i) => {
        const on = i === current;
        const past = i < current;
        return (
          <li
            key={key}
            aria-current={on ? "step" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-full py-1.5 pr-3 pl-1.5 text-[13px] font-medium",
              on
                ? "bg-foreground text-background"
                : past
                  ? "bg-card text-tone-info-fg"
                  : "bg-card text-muted-foreground",
            )}
          >
            <span
              className={cn(
                "flex size-6 items-center justify-center rounded-full font-mono text-xs",
                on ? "bg-background text-foreground" : past ? "bg-tone-info-bg" : "bg-muted",
              )}
            >
              {past ? <Check className="size-3.5" aria-hidden /> : i + 1}
            </span>
            {t(`steps.${key}`)}
          </li>
        );
      })}
    </ol>
  );
}

export default function SetupPage() {
  const { t } = useTranslation("setup");
  const { t: tc } = useTranslation();
  const profile = useMachineProfile();
  const demoMachine = useDemoMachine();
  const p = profile.data;

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-5 px-6 pt-7 pb-14">
      <Steps phase={p?.phase ?? "idle"} />
      <PageHeader
        title={t("title")}
        lead={t("lead")}
        className="items-end"
        actions={
          DEMO_DATA && p ? (
            <div className="flex flex-col gap-1.5">
              <div className="text-xs text-muted-foreground">{t("demoMachine")}</div>
              <SegmentedControl
                label={t("demoMachine")}
                value={p.machine.os === "macos" ? "mac" : "pc"}
                onChange={(m) =>
                  demoMachine.mutate(m, { onError: (err) => toast.error(errorMessage(tc, err)) })
                }
                options={(["pc", "mac"] as const).map((m) => ({
                  value: m,
                  label: t(`machine.${m}`),
                }))}
              />
            </div>
          ) : null
        }
      />
      <QueryState query={profile} skeleton={<Skeleton className="h-72 w-full" />}>
        {(data) => <SetupFlow key={data.machine.os} profile={data} />}
      </QueryState>
    </div>
  );
}

function SetupFlow({ profile: p }: { profile: MachineProfile }) {
  const { t } = useTranslation("setup");
  const { t: tc } = useTranslation();
  const nameOf = useItemName();
  const scan = useScan();
  const install = useInstall();
  const retry = useRetrySetupItem();
  const skip = useSkipSetupItem();
  const [selected, setSelected] = useState<Set<string> | null>(null);
  const [mirror, setMirror] = useState<Mirror | null>(null);
  const [dir, setDir] = useState<string | null>(null);
  const [log, setLog] = useState<SetupLog[]>([]);

  useEffect(
    () =>
      onEvent("setup.log", (data) => {
        const line = SetupLogSchema.safeParse(data);
        if (line.success) setLog((l) => [...l, line.data]);
      }),
    [],
  );

  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const sel = selected ?? new Set(requiredIds(p.items));
  const chosenMirror = mirror ?? p.install?.mirror ?? "auto";
  const chosenDir = dir ?? p.install?.dir ?? p.default_dir;
  const busy = p.phase === "scanning" || p.phase === "installing";
  const itemName = (id: string) => {
    const x = p.items.find((i) => i.id === id);
    return x ? nameOf(x) : id;
  };

  const startScan = () => {
    setSelected(null);
    scan.mutate(undefined, { onError });
  };
  const startInstall = () => {
    setLog([]);
    install.mutate({ items: [...sel], mirror: chosenMirror, dir: chosenDir }, { onError });
  };

  if (p.phase === "idle")
    return (
      <section
        aria-labelledby="will-check"
        className="flex flex-col gap-4 rounded-xl border bg-card p-6"
      >
        <h2 id="will-check" className="text-lg font-bold">
          {t("willCheck")}
        </h2>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
          {GROUPS.map((g) => (
            <div key={g} className="flex flex-col gap-1 rounded-lg bg-muted/60 px-3.5 py-3">
              <div className="text-sm font-bold">{t(`group.${g}.name`)}</div>
              <div className="text-[13px] leading-relaxed text-muted-foreground">
                {t(`group.${g}.check`)}
              </div>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="lg" disabled={scan.isPending} onClick={startScan}>
            {t("startScan")}
          </Button>
          <span className="text-[13px] text-muted-foreground">{t("scanNote")}</span>
        </div>
      </section>
    );

  const queue = p.install?.items ?? [];
  const queued = p.items.filter((x) => queue.includes(x.id));
  const doneN = queued.filter((x) => x.install?.state === "done").length;
  const failed = queued.filter(
    (x) => x.install?.state === "failed" || x.install?.state === "skipped",
  );
  const pct = overallPct(p);

  return (
    <>
      <section
        aria-label={t("summary")}
        className="flex flex-col gap-2.5 rounded-xl border bg-card px-4 py-3.5"
      >
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2">
          <span className="text-[15px] font-bold" role="status">
            {t(`phase.${p.phase}`)}
          </span>
          {statusCounts(p.phase, p.items).map((c) => (
            <StatusBadge key={c.status} tone={statusTone[c.status]} icon={null}>
              {t(`status.${c.status}`)} {c.n}
            </StatusBadge>
          ))}
          <Button
            variant="outline"
            className="ml-auto"
            disabled={busy || scan.isPending}
            onClick={startScan}
          >
            {t("rescan")}
          </Button>
        </div>
        <Progress value={pct} aria-label={t("summary")} className="h-1.5 bg-muted" />
      </section>

      <ItemGroups
        phase={p.phase}
        items={p.items}
        queue={queue}
        selected={sel}
        onToggle={(id) => {
          const next = new Set(sel);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          setSelected(next);
        }}
        onRetry={(id) => retry.mutate(id, { onError })}
        onSkip={(id) => skip.mutate(id, { onError })}
        pendingId={
          retry.isPending
            ? (retry.variables ?? null)
            : skip.isPending
              ? (skip.variables ?? null)
              : null
        }
      />

      {p.phase === "scanned" ? (
        <section
          aria-labelledby="install-title"
          className="flex flex-col gap-3.5 rounded-xl border bg-card p-4.5"
        >
          <h2 id="install-title" className="text-[17px] font-bold">
            {t("installTitle")}
          </h2>
          <div className="flex flex-wrap gap-4">
            <div className="flex flex-[1_1_280px] flex-col gap-1.5">
              <Label htmlFor="setup-dir">{t("dir")}</Label>
              <Input
                id="setup-dir"
                value={chosenDir}
                onChange={(e) => setDir(e.target.value)}
                className="font-mono text-[13px]"
              />
              <div className="text-xs text-muted-foreground">{t("dirHint")}</div>
            </div>
            <div className="flex flex-[1_1_320px] flex-col gap-1.5">
              <div className="text-[13px] font-medium">{t("mirror.label")}</div>
              <SegmentedControl
                label={t("mirror.label")}
                value={chosenMirror}
                onChange={setMirror}
                className="grid grid-cols-3"
                options={MIRRORS.map((m) => ({ value: m, label: t(`mirror.name.${m}`) }))}
              />
              <div className="text-xs leading-relaxed text-muted-foreground">
                {t(`mirror.hint.${chosenMirror}`)}
              </div>
            </div>
          </div>
          <p className="text-[13px] leading-relaxed text-muted-foreground">{t("installNote")}</p>
          <div className="flex flex-wrap items-center gap-2.5">
            <Button size="lg" disabled={sel.size === 0 || install.isPending} onClick={startInstall}>
              {t("install", { count: sel.size })}
            </Button>
            <Button
              size="lg"
              variant="outline"
              onClick={() => setSelected(new Set(requiredIds(p.items)))}
            >
              {t("onlyRequired")}
            </Button>
            <Button
              size="lg"
              variant="outline"
              onClick={() => setSelected(new Set(installableIds(p.items)))}
            >
              {t("selectAll")}
            </Button>
            <Link
              to={paths.step(DEMO_SERIES, DEMO_EPISODE, "novel")}
              className="ml-auto text-sm text-primary underline-offset-4 hover:underline"
            >
              {t("skip")}
            </Link>
          </div>
        </section>
      ) : null}

      {p.phase === "installing" || p.phase === "done" ? (
        <InstallLog lines={log} itemName={itemName} />
      ) : null}

      {p.phase === "done" ? (
        <section
          aria-labelledby="done-title"
          className="flex flex-col gap-3.5 rounded-xl border-2 border-primary bg-card p-5"
        >
          <h2 id="done-title" className="text-lg font-bold">
            {t("done.title")}
          </h2>
          <p className="text-sm leading-relaxed">
            {failed.length === 0
              ? t("done.line", { done: doneN })
              : t(failed.some((x) => x.required) ? "done.lineFailedRequired" : "done.lineFailed", {
                  done: doneN,
                  failed: failed.length,
                })}
          </p>
          {p.recommendation ? (
            <div className="flex flex-col gap-1.5 rounded-lg bg-accent p-3.5">
              <div className="text-xs text-muted-foreground">{t("done.recommend")}</div>
              <div className="text-base font-bold">{t(`rec.${p.recommendation.reason}.name`)}</div>
              <div className="text-[13px] leading-relaxed">
                {t(`rec.${p.recommendation.reason}.why`)}
              </div>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2.5">
            <Button size="lg" asChild>
              <Link to={paths.spec(DEMO_SERIES)}>{t("done.enter")}</Link>
            </Button>
            <Link
              to={paths.models()}
              className="text-sm text-primary underline-offset-4 hover:underline"
            >
              {t("done.toModels")}
            </Link>
            <span className="text-xs text-muted-foreground">{t("done.later")}</span>
          </div>
        </section>
      ) : null}
    </>
  );
}
