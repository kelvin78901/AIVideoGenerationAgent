import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, post } from "@/api/client";
import type { Job, ModelCall } from "@/api/types";

export const jobKeys = { all: ["jobs"] as const };
export const callKeys = { all: ["model-calls"] as const };
export const healthKeys = { all: ["health"] as const };

export interface Health {
  status: string;
  version: string;
  /** True unless the backend runs with DRAMA_MOCK=0. */
  mock: boolean;
}

export function useHealth() {
  return useQuery({ queryKey: healthKeys.all, queryFn: () => api<Health>("/health") });
}

export function useJobs() {
  return useQuery({ queryKey: jobKeys.all, queryFn: () => api<Job[]>("/jobs?limit=200") });
}

export function useModelCalls() {
  return useQuery({
    queryKey: callKeys.all,
    queryFn: () => api<ModelCall[]>("/dev/model-calls?limit=200"),
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
    mutationFn: (body: { prompt?: string; delay_s?: number }) => post<Job>("/dev/llm-test", body),
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
