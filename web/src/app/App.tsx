import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { BrowserRouter } from "react-router";

import { apiSpend, gpuStatus, useHealth, useJobs, useModelCalls } from "@/api/hooks/useJobs";
import { makeQueryClient } from "@/api/queryClient";
import { useEventStream } from "@/api/useEventStream";
import { AppRoutes } from "@/app/routes";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useUiStore } from "@/stores/ui";

function useThemeClass(): void {
  const theme = useUiStore((s) => s.theme);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
}

/** Routes plus the live data the shell shows (GPU queue, API spend), kept fresh over SSE. */
export function LiveRoutes() {
  useEventStream();
  const jobs = useJobs();
  const calls = useModelCalls();
  const health = useHealth();
  const gpu = gpuStatus(jobs.data);
  return (
    <AppRoutes
      status={{
        gpuRunning: gpu.running,
        gpuQueued: gpu.queued,
        spentUsd: calls.data ? apiSpend(calls.data) : null,
        budgetUsd: null,
        mock: health.data?.mock ?? null,
      }}
    />
  );
}

export function App() {
  useThemeClass();
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <TooltipProvider>
          <LiveRoutes />
          <Toaster />
        </TooltipProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
