import { Navigate, Route, Routes } from "react-router";

import { AppShell, type ShellStatus } from "@/app/AppShell";
import { DEMO_EPISODE, DEMO_SERIES, paths } from "@/app/paths";
import AssetsPage from "@/pages/Assets";
import DevJobsPage from "@/pages/DevJobs";
import DashboardPage from "@/pages/Dashboard";
import GeneratePage from "@/pages/Generate";
import LegacyPage from "@/pages/Legacy";
import ModelsPage from "@/pages/Models";
import NotFoundPage from "@/pages/NotFound";
import NovelPage from "@/pages/Novel";
import PostPage from "@/pages/Post";
import ScriptPage from "@/pages/Script";
import SetupPage from "@/pages/Setup";
import SpecPage from "@/pages/Spec";
import StoryboardPage from "@/pages/Storyboard";
import SyncPage from "@/pages/Sync";

export function AppRoutes({ status }: { status?: ShellStatus }) {
  return (
    <Routes>
      <Route path="/legacy/*" element={<LegacyPage />} />
      <Route element={<AppShell status={status} />}>
        <Route
          index
          element={<Navigate to={paths.step(DEMO_SERIES, DEMO_EPISODE, "novel")} replace />}
        />
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
        {import.meta.env.DEV ? <Route path="dev/jobs" element={<DevJobsPage />} /> : null}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
