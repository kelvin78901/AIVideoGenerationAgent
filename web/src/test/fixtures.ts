import type { Job, ModelCall } from "@/api/types";

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "a1b2c3d4e5f6",
    series_id: null,
    product_id: null,
    component_id: "script",
    kind: "dev.llm_test",
    queue: "api:deepseek",
    state: "queued",
    priority: 0,
    attempt: 0,
    max_attempts: 1,
    params: {},
    result: null,
    error: null,
    depends_on: [],
    est_cost_usd: null,
    fallback_from_job_id: null,
    created_at: "2026-10-14T10:00:00+00:00",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

export function makeCall(overrides: Partial<ModelCall> = {}): ModelCall {
  return {
    id: 1,
    job_id: "a1b2c3d4e5f6",
    component_id: "script",
    provider_id: "deepseek",
    model_key: "deepseek/v4-pro",
    where: "api",
    is_fallback: false,
    fallback_reason: null,
    status: "success",
    error_code: null,
    tokens_in: 12,
    tokens_out: 34,
    cost_usd: 0.25,
    billed: true,
    started_at: "2026-10-14T10:00:01+00:00",
    finished_at: "2026-10-14T10:00:04+00:00",
    ...overrides,
  };
}
