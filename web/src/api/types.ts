/** Shapes returned by the backend (`job_public`, `call_public` in the Python code). */

export type JobState =
  "queued" | "waiting_confirm" | "running" | "succeeded" | "failed" | "canceled";

export interface ApiErrorBody {
  code: string;
  params: Record<string, unknown>;
}

export interface Job {
  id: string;
  series_id: string | null;
  product_id: string | null;
  component_id: string | null;
  kind: string;
  queue: string;
  state: JobState;
  priority: number;
  attempt: number;
  max_attempts: number;
  params: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: ApiErrorBody | null;
  depends_on: string[];
  est_cost_usd: number | null;
  fallback_from_job_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ModelCall {
  id: number;
  job_id: string | null;
  component_id: string | null;
  provider_id: string | null;
  model_key: string;
  where: "local" | "api";
  is_fallback: boolean;
  fallback_reason: string | null;
  status: "success" | "error" | "timeout" | "canceled";
  error_code: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number;
  billed: boolean;
  started_at: string | null;
  finished_at: string | null;
}
