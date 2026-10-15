import {
  ChartNoAxesColumn,
  FlaskConical,
  Grid2x2Plus,
  Moon,
  SlidersHorizontal,
  Smartphone,
  Sun,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useParams } from "react-router";

import { DEMO_EPISODE, DEMO_SERIES, paths, STEPS } from "@/app/paths";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

/** Shown in the spec tag until M1 reads the series' real output_spec. */
const DEFAULT_SPEC_TAG = "9:16 · 1080×1920 · 24 fps";

export interface ShellStatus {
  gpuRunning: number;
  gpuQueued: number;
  spentUsd: number | null;
  budgetUsd: number | null;
  /** Backend runs mock adapters (DRAMA_MOCK != 0); null until /health answers. */
  mock?: boolean | null;
}

const IDLE: ShellStatus = { gpuRunning: 0, gpuQueued: 0, spentUsd: null, budgetUsd: null };

function usd(value: number): string {
  return `$${value.toFixed(2)}`;
}

function TopBar({ series, status }: { series: string; status: ShellStatus }) {
  const { t } = useTranslation();
  const toggleLang = useUiStore((s) => s.toggleLang);
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  const busy = status.gpuRunning + status.gpuQueued > 0;
  const gpu = busy
    ? t("shell.gpuBusy", { running: status.gpuRunning, queued: status.gpuQueued })
    : t("shell.gpuIdle");

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
      <div className="text-sm text-topbar-muted">{t("shell.noSeries")}</div>
      <NavLink
        to={paths.spec(series)}
        title={t("shell.specTagTitle")}
        className="inline-flex min-h-7 items-center rounded-full border border-topbar-border px-2.5 font-mono text-xs hover:bg-white/10"
      >
        {DEFAULT_SPEC_TAG}
      </NavLink>
      <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[13px] text-topbar-muted">
        <span data-testid="gpu-status">{t("shell.gpu", { status: gpu })}</span>
        <span>
          {t("shell.spend")} <b className="font-medium text-white">{usd(status.spentUsd ?? 0)}</b>
          {" / "}
          {status.budgetUsd != null
            ? t("shell.budget", { budget: usd(status.budgetUsd) })
            : t("shell.noBudget")}
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

function SideNav({ series, episode }: { series: string; episode: string }) {
  const { t } = useTranslation("nav");
  return (
    <nav
      aria-label={t("stepsLabel")}
      className="flex w-52 shrink-0 flex-col gap-1 border-r border-sidebar-border bg-sidebar px-3 py-4"
    >
      <div className="px-2.5 pb-1.5 text-xs text-muted-foreground">{t("stepsLabel")}</div>
      {STEPS.map((step, i) => (
        <NavLink key={step} to={paths.step(series, episode, step)} className={navItem}>
          <span className="w-5 font-mono text-xs text-muted-foreground">
            {String(i + 1).padStart(2, "0")}
          </span>
          <span>{t(`steps.${step}`)}</span>
        </NavLink>
      ))}
      <div className="my-2 h-px bg-sidebar-border" />
      <ToolLink to={paths.spec(series)} icon={Smartphone} label={t("spec")} />
      <ToolLink to={paths.models()} icon={SlidersHorizontal} label={t("models")} />
      <ToolLink to={paths.sync(series)} icon={Grid2x2Plus} label={t("sync")} />
      <ToolLink to={paths.dashboard(series)} icon={ChartNoAxesColumn} label={t("dashboard")} />
      {import.meta.env.DEV ? (
        <>
          <div className="mt-auto" />
          <ToolLink to={paths.devJobs()} icon={Wrench} label={t("devJobs")} />
        </>
      ) : null}
    </nav>
  );
}

export function AppShell({ status = IDLE }: { status?: ShellStatus }) {
  const { t } = useTranslation();
  const params = useParams();
  const series = params.series ?? DEMO_SERIES;
  const episode = params.ep ?? DEMO_EPISODE;
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-card focus:p-2"
      >
        {t("shell.skipToContent")}
      </a>
      <TopBar series={series} status={status} />
      <div className="flex flex-1">
        <SideNav series={series} episode={episode} />
        <main id="main" className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
