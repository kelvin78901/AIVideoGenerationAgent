import { Navigate, Route, Routes } from "react-router";

import { useSeriesList } from "@/api/hooks/series";
import { useMachineProfile } from "@/api/hooks/setup";
import { AppShell, type ShellStatus } from "@/app/AppShell";
import { DEMO_EPISODE, DEMO_SERIES, paths } from "@/app/paths";
import AssetsPage from "@/pages/Assets";
import DevComponentsPage from "@/pages/DevComponents";
import DevJobsPage from "@/pages/DevJobs";
import DashboardPage from "@/pages/Dashboard";
import GeneratePage from "@/pages/Generate";
import LegacyPage from "@/pages/Legacy";
import ModelsPage from "@/pages/Models";
import NoSeriesPage from "@/pages/NoSeries";
import NotFoundPage from "@/pages/NotFound";
import NovelPage from "@/pages/Novel";
import PostPage from "@/pages/Post";
import ScriptPage from "@/pages/Script";
import SetupPage from "@/pages/Setup";
import SpecPage from "@/pages/Spec";
import StoryboardPage from "@/pages/Storyboard";
import SyncPage from "@/pages/Sync";
import { useUiStore } from "@/stores/ui";

/**
 * `/` opens the first-run page until a scan has finished (SPEC 16.1), otherwise the series
 * opened last (else the newest), or a page to start one when there is none. Deep links never
 * jump; if the profile or the list cannot be read, the workbench opens anyway.
 */
function HomeRedirect() {
  const profile = useMachineProfile();
  const list = useSeriesList();
  const last = useUiStore((s) => s.lastSeries);
  if (profile.isPending) return null;
  if (profile.data?.scanned_at === null) return <Navigate to={paths.setup()} replace />;
  if (list.isPending) return null;
  const ids = list.data?.map((s) => s.id) ?? [];
  if (list.isSuccess && !ids.length) return <NoSeriesPage />;
  const series = last && ids.includes(last) ? last : (ids[0] ?? last ?? DEMO_SERIES);
  return <Navigate to={paths.step(series, DEMO_EPISODE, "novel")} replace />;
}

export function AppRoutes({ status }: { status?: ShellStatus }) {
  return (
    <Routes>
      <Route path="/legacy/*" element={<LegacyPage />} />
      <Route element={<AppShell status={status} />}>
        <Route index element={<HomeRedirect />} />
        <Route path="setup" element={<SetupPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="s/:series">
          <Route path="spec" element={<SpecPage />} />
          <Route path="sync" element={<SyncPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="e/:ep">
            <Route path="novel" element={<NovelPage />} />
            <Route path="script" element={<ScriptPage />} />
            <Route path="assets" element={<AssetsPage />} />
            <Route path="storyboard" element={<StoryboardPage />} />
            <Route path="generate" element={<GeneratePage />} />
            <Route path="post" element={<PostPage />} />
          </Route>
        </Route>
        {import.meta.env.DEV ? (
          <>
            <Route path="dev/jobs" element={<DevJobsPage />} />
            <Route path="dev/components" element={<DevComponentsPage />} />
          </>
        ) : null}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
