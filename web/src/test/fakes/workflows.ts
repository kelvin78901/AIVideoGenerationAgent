/**
 * Fake 工作流库 for page tests: the repo's workflows on the sample ComfyUI after 全部体检, and
 * two more its workflow list offers for import (`test/data/workflows.json`, written by
 * tests/api/test_web_fixtures.py), following `wflib/service.py` as far as the page needs it:
 * - importing from ComfyUI's list adds that workflow as the backend imported it (guessed
 *   bindings, checked); the asset board and imported ones are refused; a dropped API-format
 *   JSON comes in with no bindings;
 * - saving bindings confirms them (and demotes 我的工作流); repo workflows refuse it;
 * - 我的工作流 needs confirmed bindings and a passed trial; repo workflows keep their tier;
 * - installing what is missing takes a snapshot and installs the node packs; model files stay
 *   listed (the user puts them in place);
 * - a trial starts a `workflow_trial` job (`job.updated`); `finishFakeTrial()` ends it.
 */
import { http, HttpResponse } from "msw";
import { z } from "zod";

import { injectEvent } from "@/api/events";
import type { Message } from "@/api/schemas/common";
import type { Job } from "@/api/schemas/jobs";
import {
  BindingSchema,
  ComfyWorkflowFileSchema,
  ImportRequestSchema,
  WorkflowSchema,
  WorkflowTierSchema,
  type ComfyWorkflowFile,
  type Workflow,
} from "@/api/schemas/workflows";
import data from "@/test/data/workflows.json";

const exported = z.array(WorkflowSchema).parse(data.workflows);
const files = z.array(ComfyWorkflowFileSchema).parse(data.comfy_files);
const deps = data.deps as Record<string, Message[]>;
/** Imported from ComfyUI's list in the export; the library starts without them. */
const importable = new Map(exported.filter((w) => w.origin).map((w) => [w.origin, w]));

/** State of the fake; `resetFakeWorkflows()` (called by `backend()`) restores it. */
export const fakeWorkflows = {
  workflows: [] as Workflow[],
  files: [] as ComfyWorkflowFile[],
  /** Trial jobs started, by workflow id. */
  trials: {} as Record<string, Job>,
};

export function resetFakeWorkflows() {
  fakeWorkflows.workflows = structuredClone(exported.filter((w) => !w.origin));
  fakeWorkflows.files = files.map((f) => ({ ...structuredClone(f), imported_as: null }));
  fakeWorkflows.trials = {};
}

/** Puts a workflow from ComfyUI's list in the library, as importing it would. */
export function fakeImport(origin: string): Workflow {
  const w = importable.get(origin);
  const file = fakeWorkflows.files.find((f) => f.path === origin);
  if (!w || !file) throw new Error(`${origin} is not in the export`);
  const copy = structuredClone(w);
  fakeWorkflows.workflows.push(copy);
  file.imported_as = copy.id;
  return copy;
}

const now = () => new Date().toISOString();
const find = (id: string) => fakeWorkflows.workflows.find((w) => w.id === id);
const pending = (w: Workflow) => w.bindings.filter((b) => b.state === "guessed").length;
const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

function trialJob(w: Workflow, state: Job["state"]): Job {
  const at = now();
  return {
    id: `job_trial_${w.id}`,
    series_id: null,
    product_id: null,
    component_id: w.components[0] ?? null,
    kind: "workflow_trial",
    queue: "gpu",
    state,
    priority: 0,
    attempt: 1,
    max_attempts: 1,
    params: { workflow_id: w.id, model_key: w.model_key },
    result: null,
    error: null,
    depends_on: [],
    est_cost_usd: null,
    fallback_from_job_id: null,
    created_at: at,
    started_at: at,
    finished_at: state === "running" ? null : at,
  };
}

/** The sampler's steps on the running trial, as ComfyUI reports them. */
export function fakeTrialProgress(id: string, step: number, steps: number) {
  const job = fakeWorkflows.trials[id];
  if (!job) throw new Error(`no trial running for ${id}`);
  injectEvent("job.updated", {
    ...job,
    progress: { take: 1, takes: 1, step, steps, pct: step / steps },
  });
}

/** The trial job ends: the row has its result, then `job.updated` says so. */
export function finishFakeTrial(id: string, status: "passed" | "failed" = "passed") {
  const w = find(id);
  const job = fakeWorkflows.trials[id];
  if (!w?.trial || !job) throw new Error(`no trial running for ${id}`);
  const passed = status === "passed";
  w.trial = {
    ...w.trial,
    at: now(),
    status,
    duration_s: passed ? 41 : null,
    vram_gb: passed ? 22.4 : null,
    error: passed ? null : { code: "comfy_failed", params: {} },
  };
  w.updated_at = now();
  injectEvent("job.updated", {
    ...job,
    state: passed ? "succeeded" : "failed",
    finished_at: now(),
  });
}

/** A dropped API-format JSON: its nodes by title, nothing bound yet. */
function dropped(fileName: string, graph: Record<string, unknown>): Workflow {
  const name = fileName.replace(/\.json$/i, "");
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "workflow";
  const nodes = Object.values(graph).map((n) => {
    const node = n as { class_type: string; inputs?: object; _meta?: { title?: string } };
    return {
      title: node._meta?.title ?? node.class_type,
      class_type: node.class_type,
      fields: Object.keys(node.inputs ?? {}),
    };
  });
  const at = now();
  return {
    ...structuredClone(importable.get("sdxl_basic.json") ?? exported[0]),
    id: `wf_${slug}`,
    slug,
    model_key: `comfy/${slug}`,
    name,
    origin: fileName,
    bindings: [],
    nodes,
    created_at: at,
    updated_at: at,
  } as Workflow;
}

export function workflowHandlers() {
  return [
    http.get("*/api/v1/workflows", () => HttpResponse.json(fakeWorkflows.workflows)),
    http.get<{ id: string }>("*/api/v1/workflows/:id", ({ params }) => {
      const w = find(params.id);
      return w ? HttpResponse.json(w) : error(404, "workflow_not_found", { id: params.id });
    }),
    http.get("*/api/v1/comfy/workflows", () => HttpResponse.json(fakeWorkflows.files)),

    http.post("*/api/v1/workflows/import", async ({ request }) => {
      const body = ImportRequestSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const origin = "comfy_path" in body.data ? body.data.comfy_path : body.data.file_name;
      const file = fakeWorkflows.files.find((f) => f.path === origin);
      if (file?.board) return error(409, "workflow_is_board");
      const same = fakeWorkflows.workflows.find((w) => w.origin === origin);
      if (same) return error(409, "workflow_imported", { id: same.id });
      const listed = importable.get(origin);
      const w =
        "comfy_path" in body.data
          ? listed && structuredClone(listed)
          : dropped(body.data.file_name, body.data.workflow);
      if (!w) return error(409, "comfy_not_running");
      fakeWorkflows.workflows.push(w);
      if (file) file.imported_as = w.id;
      return HttpResponse.json(w, { status: 201 });
    }),

    http.patch<{ id: string }>("*/api/v1/workflows/:id", async ({ params, request }) => {
      const body = z.object({ tier: WorkflowTierSchema }).safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const w = find(params.id);
      if (!w) return error(404, "workflow_not_found", { id: params.id });
      const tier = body.data.tier;
      if (tier === "recommended" || w.source === "repo") return error(409, "workflow_tier_repo");
      if (tier === "mine") {
        if (pending(w)) return error(409, "workflow_bindings_pending", { count: pending(w) });
        if (w.trial?.status !== "passed" || w.file_changed)
          return error(409, "workflow_needs_trial");
      }
      Object.assign(w, { tier, updated_at: now() });
      return HttpResponse.json(w);
    }),

    http.put<{ id: string }>("*/api/v1/workflows/:id/bindings", async ({ params, request }) => {
      const body = z.array(BindingSchema).safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const w = find(params.id);
      if (!w) return error(404, "workflow_not_found", { id: params.id });
      if (w.uses_dramastudio_nodes) return error(409, "workflow_dramastudio_bindings");
      if (w.source === "repo") return error(409, "workflow_tier_repo");
      const classes = new Map(w.nodes.map((n) => [n.title, n.class_type]));
      const bad = body.data.find((b) => !classes.has(b.node_title));
      if (bad) return error(422, "workflow_unknown_node", { title: bad.node_title });
      w.bindings = body.data.map((b) => ({
        ...b,
        state: "confirmed" as const,
        node_class: classes.get(b.node_title) ?? b.node_class,
      }));
      if (w.tier === "mine") w.tier = "unverified"; // a different binding is a different workflow
      w.updated_at = now();
      return HttpResponse.json(w);
    }),

    http.post<{ id: string }>("*/api/v1/workflows/:id/check", ({ params }) => {
      const w = find(params.id);
      if (!w) return error(404, "workflow_not_found", { id: params.id });
      if (w.check) w.check.at = now();
      return HttpResponse.json(w);
    }),
    http.post("*/api/v1/workflows/check-all", () => {
      for (const w of fakeWorkflows.workflows) if (w.check) w.check.at = now();
      return HttpResponse.json(fakeWorkflows.workflows);
    }),

    http.post<{ id: string }>("*/api/v1/workflows/:id/deps", ({ params }) => {
      const w = find(params.id);
      if (!w) return error(404, "workflow_not_found", { id: params.id });
      return HttpResponse.json({
        changes: w.check?.status === "missing" ? (deps[w.id] ?? []) : [],
      });
    }),
    http.post<{ id: string }>("*/api/v1/workflows/:id/deps/install", ({ params }) => {
      const w = find(params.id);
      if (!w?.check) return error(404, "workflow_not_found", { id: params.id });
      const packs = w.check.missing_packs.length;
      if (!packs) return error(409, "workflow_nothing_to_install");
      const total = w.check.node_classes.total;
      // Model files stay listed: the user puts them in place.
      w.check = {
        ...w.check,
        at: now(),
        status: w.check.missing_models.length ? "missing" : "ok",
        node_classes: { found: total, total },
        missing_packs: [],
      };
      w.updated_at = now();
      return HttpResponse.json({
        workflow: w,
        packs,
        models: 0,
        snapshot: "2026-10-18_10-05-00_snapshot",
        restart_required: false,
        failed: [],
      });
    }),

    http.post<{ id: string }>("*/api/v1/workflows/:id/trial", ({ params }) => {
      const w = find(params.id);
      if (!w) return error(404, "workflow_not_found", { id: params.id });
      if (pending(w)) return error(409, "workflow_bindings_pending", { count: pending(w) });
      if (w.check?.status !== "ok") return error(409, "workflow_check_failed");
      const job = trialJob(w, "running");
      fakeWorkflows.trials[w.id] = job;
      w.trial = {
        at: now(),
        status: "running",
        job_id: job.id,
        w: 768,
        h: 1366,
        seconds: w.components.includes("vid") ? 3 : 0,
        duration_s: null,
        vram_gb: null,
        error: null,
      };
      injectEvent("job.updated", job);
      return HttpResponse.json(w, { status: 202 });
    }),
  ];
}
