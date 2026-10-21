import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, post } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import type { StepId } from "@/api/schemas/episodes";
import {
  HealthSchema,
  JobSchema,
  ModelCallSchema,
  type Job,
  type JobState,
  type ModelCall,
} from "@/api/schemas/jobs";

export const jobKeys = { all: ["jobs"] as const };
const ACTIVE = new Set<JobState>(["queued", "waiting_confirm", "running"]);
export const callKeys = { all: ["model-calls"] as const };
export const healthKeys = { all: ["health"] as const };

export function useHealth() {
  return useQuery({ queryKey: healthKeys.all, queryFn: () => api("/health", HealthSchema) });
}

export function useJobs() {
  return useQuery({
    queryKey: jobKeys.all,
    queryFn: () => api("/jobs?limit=200", z.array(JobSchema)),
  });
}

export function useModelCalls() {
  return useQuery({
    queryKey: callKeys.all,
    queryFn: () => api("/dev/model-calls?limit=200", z.array(ModelCallSchema)),
  });
}

/** Insert or replace one job in the cached list (newest first), as `job.updated` arrives. */
export function upsertJob(client: QueryClient, job: Job): void {
  client.setQueryData<Job[]>(jobKeys.all, (old) => {
    if (!old) return old; // not loaded yet; the first fetch will include it
    const rest = old.filter((j) => j.id !== job.id);
    return [job, ...rest].sort((a, b) => b.created_at.localeCompare(a.created_at));
  });
}

function useJobAction(action: "confirm" | "cancel") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => post(`/jobs/${id}/${action}`, JobSchema, {}),
    onSuccess: (job) => {
      upsertJob(client, job);
      void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

/** 「确认，开始运行」 on a run waiting for a yes. */
export const useConfirmJob = () => useJobAction("confirm");
/** 「取消这次运行」. */
export const useCancelJob = () => useJobAction("cancel");

export function useLlmTest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { prompt?: string; delay_s?: number }) =>
      post("/dev/llm-test", JobSchema, body),
    onSuccess: (job) => upsertJob(client, job),
  });
}

export interface GpuStatus {
  running: number;
  queued: number;
}

export function gpuStatus(jobs: Job[] | undefined): GpuStatus {
  const gpu = (jobs ?? []).filter((j) => j.queue === "gpu");
  return {
    running: gpu.filter((j) => j.state === "running").length,
    queued: gpu.filter((j) => j.state === "queued").length,
  };
}

/** The production step a component's product shows under (the left navigation). */
const COMPONENT_STEP: Partial<Record<string, StepId>> = {
  enrich: "novel",
  extract: "novel",
  split: "script",
  script: "script",
};

/**
 * Steps of this episode with a 确认并同步 rerun still queued, waiting or running (「同步中」):
 * series-level products count for every episode, an episode's only for itself.
 */
export function syncingSteps(
  jobs: Job[] | undefined,
  seriesId: string,
  episodeId: string | undefined,
): Set<StepId> {
  const steps = new Set<StepId>();
  for (const j of jobs ?? []) {
    if (!ACTIVE.has(j.state) || j.series_id !== seriesId || !j.params.cascade) continue;
    if (j.episode_id && j.episode_id !== episodeId) continue;
    const step = COMPONENT_STEP[j.component_id ?? ""];
    if (step) steps.add(step);
  }
  return steps;
}

/** Billed API spend over the loaded calls. M8 replaces this with `/metrics/summary`. */
export function apiSpend(calls: ModelCall[] | undefined): number {
  return (calls ?? [])
    .filter((c) => c.billed && c.where === "api")
    .reduce((s, c) => s + c.cost_usd, 0);
}
