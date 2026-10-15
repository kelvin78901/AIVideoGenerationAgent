import {
  ChartNoAxesColumn,
  Database,
  FlaskConical,
  Grid2x2Plus,
  Moon,
  SlidersHorizontal,
  Smartphone,
  Sun,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useLayoutEffect } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation } from "react-router";

import {
  useEpisodeProgress,
  useMetricsSummary,
  useOutputSpec,
  useRouteEpisode,
  useSeries,
} from "@/api/hooks/series";
import { useMachineProfile } from "@/api/hooks/setup";
import type { StepProgress } from "@/api/schemas/episodes";
import { paths, STEPS } from "@/app/paths";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatSpecTag, formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useDemoStore } from "@/stores/demo";
import { useUiStore } from "@/stores/ui";

/** Live backend state the shell shows; the rest of the top bar comes from API hooks. */
export interface ShellStatus {
  gpuRunning: number;
  gpuQueued: number;
  /** Backend runs mock adapters (DRAMA_MOCK != 0); null until /health answers. */
  mock?: boolean | null;
}

const IDLE: ShellStatus = { gpuRunning: 0, gpuQueued: 0 };

/** Shown while the current route has displayed MSW demo data (stores/demo.ts). */
function DemoBadge() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const shown = useDemoStore((s) => s.routes[pathname] === true);
  if (!shown) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          data-testid="demo-badge"
          tabIndex={0}
          className="inline-flex items-center gap-1 rounded-md bg-status-info px-2 py-0.5 text-xs font-bold tracking-wide text-white"
        >
          <Database className="size-3.5" aria-hidden />
          {t("shell.demoBadge")}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-72">{t("shell.demoBadgeTitle")}</TooltipContent>
    </Tooltip>
  );
}

/** Tells the demo store which route is on screen, before children start fetching. */
function useTrackRoute(): void {
  const { pathname } = useLocation();
  const setRoute = useDemoStore((s) => s.setRoute);
  useLayoutEffect(() => setRoute(pathname), [pathname, setRoute]);
}

function TopBar({ status }: { status: ShellStatus }) {
  const { t } = useTranslation();
  const { seriesId, episode } = useRouteEpisode();
  const series = useSeries(seriesId);
  const spec = useOutputSpec(seriesId);
  const summary = useMetricsSummary("episode", episode?.id);
  const profile = useMachineProfile();
  const toggleLang = useUiStore((s) => s.toggleLang);
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);

  const busy = status.gpuRunning + status.gpuQueued > 0;
  const gpuState = busy
    ? t("shell.gpuBusy", { running: status.gpuRunning, queued: status.gpuQueued })
    : t("shell.gpuIdle");
  const gpu = profile.data?.machine.gpu;
  const specData = spec.data;
  const spent = summary.data?.spent_usd;
  const budget = summary.data?.budget_usd ?? episode?.budget_usd ?? null;

  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-2 bg-topbar px-5 py-2.5 text-topbar-foreground">
      <div className="text-[15px] font-bold tracking-wide">{t("app.name")}</div>
      {status.mock ? (
        <span
          data-testid="mock-badge"
          title={t("shell.mockBadgeTitle")}
          className="inline-flex items-center gap-1 rounded-md bg-status-warn px-2 py-0.5 text-xs font-bold tracking-wide text-white uppercase"
        >
          <FlaskConical className="size-3.5" aria-hidden />
          {t("shell.mockBadge")}
        </span>
      ) : null}
      <DemoBadge />
      <div className="text-sm text-topbar-muted" data-testid="shell-title">
        {series.data ? t("shell.seriesTitle", { title: series.data.title }) : t("shell.noSeries")}
        {series.data && episode ? (
          <>
            {" · "}
            {t("shell.episodeTitle", { n: episode.idx, title: episode.title })}
          </>
        ) : null}
      </div>
      {specData ? (
        <NavLink
          to={paths.spec(seriesId)}
          title={t("shell.specTagTitle")}
          className="inline-flex min-h-7 items-center rounded-full border border-topbar-border px-2.5 font-mono text-xs hover:bg-white/10"
        >
          {formatSpecTag(
            specData.aspect,
            specData.dims.delivery.w,
            specData.dims.delivery.h,
            specData.fps,
          )}
        </NavLink>
      ) : null}
      <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[13px] text-topbar-muted">
        <span data-testid="gpu-status">
          {gpu
            ? t("shell.gpuNamed", { name: gpu.name, vram: gpu.vram_gb, status: gpuState })
            : t("shell.gpu", { status: gpuState })}
        </span>
        <span data-testid="spend">
          {t("shell.spend")}{" "}
          <b className="font-medium text-topbar-foreground">
            {spent != null ? formatUsd(spent) : "—"}
          </b>
          {" / "}
          {budget != null ? t("shell.budget", { budget: formatUsd(budget) }) : t("shell.noBudget")}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleLang}
          aria-label={t("shell.langToggleLabel")}
          className="border border-topbar-border text-topbar-foreground hover:bg-white/10 hover:text-topbar-foreground"
        >
          {t("shell.langToggle")}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={t("shell.themeToggleLabel")}
          className="size-7 text-topbar-foreground hover:bg-white/10 hover:text-topbar-foreground"
        >
          {theme === "dark" ? <Sun /> : <Moon />}
        </Button>
      </div>
    </header>
  );
}

const navItem = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-h-10 items-center gap-2.5 rounded-md border border-transparent px-2.5 text-sidebar-foreground hover:bg-sidebar-accent/60",
    isActive && "border-sidebar-border bg-card font-semibold text-foreground shadow-xs",
  );

function ToolLink({ to, icon: Icon, label }: { to: string; icon: LucideIcon; label: string }) {
  return (
    <NavLink to={to} className={navItem}>
      <Icon className="size-4 text-muted-foreground" aria-hidden />
      <span>{label}</span>
    </NavLink>
  );
}

/** 已确认 / 7/13 / 未开始 / 待更新 N, as in the prototype's left nav. */
function StepBadge({ progress }: { progress: StepProgress | undefined }) {
  const { t } = useTranslation("nav");
  if (!progress) return null;
  let text: string;
  let tone = "bg-tone-neutral-bg text-tone-neutral-fg";
  if (progress.stale > 0) {
    text = t("badge.stale", { count: progress.stale });
    tone = "bg-tone-warn-bg text-tone-warn-fg";
  } else if (progress.state === "confirmed") {
    text = t("badge.confirmed");
    tone = "bg-tone-info-bg text-tone-info-fg";
  } else if (progress.done != null && progress.total != null) {
    text = `${progress.done}/${progress.total}`;
  } else {
    text = progress.state === "not_started" ? t("badge.notStarted") : t("badge.inProgress");
  }
  return (
    <span
      className={cn("ml-auto rounded px-1.5 py-px font-mono text-[11px] font-normal", tone)}
      data-testid="step-badge"
    >
      {text}
    </span>
  );
}

function SideNav() {
  const { t } = useTranslation("nav");
  const { seriesId, episodeIdx, episode } = useRouteEpisode();
  const progress = useEpisodeProgress(episode?.id);
  const episodeKey = String(episodeIdx);
  return (
    <nav
      aria-label={t("stepsLabel")}
      className="flex w-52 shrink-0 flex-col gap-1 border-r border-sidebar-border bg-sidebar px-3 py-4"
    >
      <div className="px-2.5 pb-1.5 text-xs text-muted-foreground">{t("stepsLabel")}</div>
      {STEPS.map((step, i) => (
        <NavLink key={step} to={paths.step(seriesId, episodeKey, step)} className={navItem}>
          <span className="w-5 font-mono text-xs text-muted-foreground">
            {String(i + 1).padStart(2, "0")}
          </span>
          <span>{t(`steps.${step}`)}</span>
          <StepBadge progress={progress.data?.steps[step]} />
        </NavLink>
      ))}
      <div className="my-2 h-px bg-sidebar-border" />
      <ToolLink to={paths.spec(seriesId)} icon={Smartphone} label={t("spec")} />
      <ToolLink to={paths.models()} icon={SlidersHorizontal} label={t("models")} />
      <ToolLink to={paths.sync(seriesId)} icon={Grid2x2Plus} label={t("sync")} />
      <ToolLink to={paths.dashboard(seriesId)} icon={ChartNoAxesColumn} label={t("dashboard")} />
      {import.meta.env.DEV ? (
        <>
          <div className="mt-auto" />
          <ToolLink to={paths.devComponents()} icon={Wrench} label={t("devComponents")} />
          <ToolLink to={paths.devJobs()} icon={Wrench} label={t("devJobs")} />
        </>
      ) : null}
    </nav>
  );
}

export function AppShell({ status = IDLE }: { status?: ShellStatus }) {
  const { t } = useTranslation();
  useTrackRoute();
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-card focus:p-2"
      >
        {t("shell.skipToContent")}
      </a>
      <TopBar status={status} />
      <div className="flex flex-1">
        <SideNav />
        <main id="main" className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
