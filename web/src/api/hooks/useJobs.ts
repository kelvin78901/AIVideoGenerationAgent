import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, post } from "@/api/client";
import {
  HealthSchema,
  JobSchema,
  ModelCallSchema,
  type Job,
  type ModelCall,
} from "@/api/schemas/jobs";

export const jobKeys = { all: ["jobs"] as const };
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

/** Billed API spend over the loaded calls. M8 replaces this with `/metrics/summary`. */
export function apiSpend(calls: ModelCall[] | undefined): number {
  return (calls ?? [])
    .filter((c) => c.billed && c.where === "api")
    .reduce((s, c) => s + c.cost_usd, 0);
}
