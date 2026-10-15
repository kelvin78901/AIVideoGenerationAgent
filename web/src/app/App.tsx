import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { BrowserRouter } from "react-router";

import { gpuStatus, useHealth, useJobs } from "@/api/hooks/useJobs";
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

/** Routes plus the live backend state the shell shows (GPU queue, mock mode), kept fresh over SSE. */
export function LiveRoutes() {
  useEventStream();
  const jobs = useJobs();
  const health = useHealth();
  const gpu = gpuStatus(jobs.data);
  return (
    <AppRoutes
      status={{
        gpuRunning: gpu.running,
        gpuQueued: gpu.queued,
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
