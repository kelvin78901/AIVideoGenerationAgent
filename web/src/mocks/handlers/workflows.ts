/**
 * Workflow library (SPEC 6.4, 9.1 `/workflows/*`; backend in M5). Import guesses bindings, a
 * health check lists what is missing, missing node packs install after the ComfyUI change list,
 * a trial run passes after `demoTiming.workflowTrialMs`, and the tier rules of 6.4.4 apply.
 */
import { http } from "msw";
import { z } from "zod";

import type { Message } from "@/api/schemas/common";
import {
  BindingSchema,
  ImportRequestSchema,
  WorkflowTierSchema,
  type Workflow,
} from "@/api/schemas/workflows";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { importedGuess, TRIAL_DRAFT } from "@/mocks/fixtures/demo/workflows";
import { demoError, demoJson, v1 } from "@/mocks/http";

const now = () => new Date().toISOString();

const find = (id: string) => getDb().workflows.find((w) => w.id === id);

const pending = (w: Workflow) => w.bindings.filter((b) => b.state === "guessed").length;

function slugOf(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return base || `workflow-${getDb().workflows.length + 1}`;
}

/** 「我的/雨夜氛围-ltx2.json」 → 「雨夜氛围-ltx2」. */
const nameOf = (path: string) => (path.split("/").pop() ?? path).replace(/\.json$/i, "");

function imported(origin: string): Workflow {
  const name = nameOf(origin);
  const slug = slugOf(name);
  const at = now();
  return structuredClone({
    id: `wf_${slug}_${getDb().workflows.length + 1}`,
    slug,
    model_key: `comfy/${slug}`,
    name,
    tier: "unverified" as const,
    source: "user" as const,
    origin,
    ...importedGuess,
    file_sha256: "5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d",
    file_changed: false,
    uses_dramastudio_nodes: false,
    check: {
      at,
      status: "ok" as const,
      node_classes: { found: 9, total: 9 },
      missing_packs: [],
      missing_models: [],
      problems: [],
    },
    trial: null,
    created_at: at,
    updated_at: at,
  });
}

function depsChanges(w: Workflow): Message[] {
  const check = w.check;
  if (!check) return [];
  return [
    ...check.missing_packs.map((p) => ({
      code: "comfy_change",
      params: {
        item: p.name,
        action: "install",
        ...(p.version ? { to: p.version } : {}),
        ...(p.url ? { source: p.url } : {}),
      },
    })),
    ...check.missing_models.map((m) => ({
      code: "comfy_change",
      params: {
        item: `${m.folder}/${m.name}`,
        action: "install",
        ...(m.url ? { source: m.url } : {}),
        ...(m.size_bytes ? { gb: Math.round((m.size_bytes / 1024 ** 3) * 10) / 10 } : {}),
      },
    })),
  ];
}

export const workflowHandlers = [
  http.get(v1("/workflows"), () => demoJson(getDb().workflows)),

  http.get<{ id: string }>(v1("/workflows/:id"), ({ params }) => {
    const w = find(params.id);
    return w ? demoJson(w) : demoError(404, "workflow_not_found", { id: params.id });
  }),

  http.get(v1("/comfy/workflows"), () => demoJson(getDb().comfyWorkflowFiles)),

  /** A dropped API-format JSON, or a workflow from ComfyUI's list; checked right away. */
  http.post(v1("/workflows/import"), async ({ request }) => {
    const body = ImportRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const d = getDb();
    const origin = "comfy_path" in body.data ? body.data.comfy_path : body.data.file_name;
    const file = d.comfyWorkflowFiles.find((f) => f.path === origin);
    if (file?.board) return demoError(409, "workflow_is_board");
    if (file?.imported_as) return demoError(409, "workflow_imported", { id: file.imported_as });
    const w = imported(origin);
    d.workflows.push(w);
    if (file) file.imported_as = w.id;
    return demoJson(w, { status: 201 });
  }),

  /** Change tiers (SPEC 6.4.4): 我的工作流 needs confirmed bindings and a passed trial. */
  http.patch<{ id: string }>(v1("/workflows/:id"), async ({ params, request }) => {
    const body = z.object({ tier: WorkflowTierSchema }).safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const w = find(params.id);
    if (!w) return demoError(404, "workflow_not_found", { id: params.id });
    const tier = body.data.tier;
    if (tier === "recommended" || w.source === "repo") return demoError(409, "workflow_tier_repo");
    if (tier === "mine") {
      if (pending(w)) return demoError(409, "workflow_bindings_pending", { count: pending(w) });
      if (w.trial?.status !== "passed" || w.file_changed)
        return demoError(409, "workflow_needs_trial");
    }
    Object.assign(w, { tier, updated_at: now() });
    return demoJson(w);
  }),

  /** Saving the bindings confirms them all (the page sends only after the user said yes). */
  http.put<{ id: string }>(v1("/workflows/:id/bindings"), async ({ params, request }) => {
    const body = z.array(BindingSchema).safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const w = find(params.id);
    if (!w) return demoError(404, "workflow_not_found", { id: params.id });
    if (w.uses_dramastudio_nodes) return demoError(409, "workflow_dramastudio_bindings");
    const known = new Set(w.nodes.map((n) => n.title));
    const bad = body.data.find((b) => !known.has(b.node_title));
    if (bad) return demoError(422, "workflow_unknown_node", { title: bad.node_title });
    w.bindings = body.data;
    // A different binding is a different workflow: the last trial no longer counts.
    if (w.trial?.status === "passed" && w.tier === "mine") w.tier = "unverified";
    w.updated_at = now();
    return demoJson(w);
  }),

  http.post<{ id: string }>(v1("/workflows/:id/check"), ({ params }) => {
    const w = find(params.id);
    if (!w) return demoError(404, "workflow_not_found", { id: params.id });
    if (w.check) w.check.at = now();
    return demoJson(w);
  }),

  http.post(v1("/workflows/check-all"), () => {
    const at = now();
    for (const w of getDb().workflows) if (w.check) w.check.at = at;
    return demoJson(getDb().workflows);
  }),

  /** What installing the missing node packs and models would change (the 6.4.1 list). */
  http.post<{ id: string }>(v1("/workflows/:id/deps"), ({ params }) => {
    const w = find(params.id);
    if (!w) return demoError(404, "workflow_not_found", { id: params.id });
    return demoJson({ changes: depsChanges(w) });
  }),

  /** Approved: snapshot first, then install; the check comes back clean. */
  http.post<{ id: string }>(v1("/workflows/:id/deps/install"), ({ params }) => {
    const w = find(params.id);
    if (!w?.check) return demoError(404, "workflow_not_found", { id: params.id });
    const packs = w.check.missing_packs.length;
    const models = w.check.missing_models.length;
    w.check = {
      ...w.check,
      at: now(),
      status: "ok",
      node_classes: { found: w.check.node_classes.total, total: w.check.node_classes.total },
      missing_packs: [],
      missing_models: [],
    };
    w.updated_at = now();
    return demoJson({ workflow: w, packs, models, snapshot: "2026-10-18_10-05-00_snapshot" });
  }),

  /** On the sample inputs, at the draft size and the shortest duration; GPU queue. */
  http.post<{ id: string }>(v1("/workflows/:id/trial"), ({ params }) => {
    const w = find(params.id);
    if (!w) return demoError(404, "workflow_not_found", { id: params.id });
    if (pending(w)) return demoError(409, "workflow_bindings_pending", { count: pending(w) });
    if (w.check?.status !== "ok") return demoError(409, "workflow_check_failed");
    const run = `job_trial_${w.id}_${Date.now()}`;
    w.trial = {
      at: now(),
      status: "running",
      job_id: run,
      ...TRIAL_DRAFT,
      duration_s: null,
      vram_gb: null,
      error: null,
    };
    setTimeout(() => {
      if (find(w.id)?.trial?.job_id !== run) return;
      w.trial = {
        ...TRIAL_DRAFT,
        at: now(),
        status: "passed",
        job_id: run,
        duration_s: 41,
        vram_gb: w.caps.vram_gb ? Math.round(w.caps.vram_gb * 8) / 10 : null,
        error: null,
      };
      w.updated_at = now();
    }, demoTiming.workflowTrialMs);
    return demoJson(w, { status: 202 });
  }),
];
