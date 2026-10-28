/** Workflow library (SPEC 6.4): list, import, bindings, health check, missing deps, trial, tier. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, patch, post, put } from "@/api/client";
import {
  ComfyWorkflowFileSchema,
  DepsPlanSchema,
  WorkflowSchema,
  type Binding,
  type ImportRequest,
  type Workflow,
  type WorkflowTier,
} from "@/api/schemas/workflows";

const enc = encodeURIComponent;

export const workflowKeys = {
  all: ["workflows"] as const,
  comfyFiles: ["comfy", "workflows"] as const,
};

/** A trial's end arrives as `job.updated` (`workflow_trial`), which refetches this list. */
export function useWorkflows() {
  return useQuery({
    queryKey: workflowKeys.all,
    queryFn: () => api("/workflows", z.array(WorkflowSchema)),
  });
}

export function useComfyWorkflowFiles({ enabled }: { enabled: boolean }) {
  return useQuery({
    queryKey: workflowKeys.comfyFiles,
    queryFn: () => api("/comfy/workflows", z.array(ComfyWorkflowFileSchema)),
    enabled,
  });
}

function useWorkflowMutation<V, R>(fn: (vars: V) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: workflowKeys.all });
      void client.invalidateQueries({ queryKey: workflowKeys.comfyFiles });
    },
  });
}

export const useImportWorkflow = () =>
  useWorkflowMutation((body: ImportRequest) => post("/workflows/import", WorkflowSchema, body));

export const useSetWorkflowTier = (id: string) =>
  useWorkflowMutation((tier: WorkflowTier) =>
    patch(`/workflows/${enc(id)}`, WorkflowSchema, { tier }),
  );

export const useSaveBindings = (id: string) =>
  useWorkflowMutation((bindings: Binding[]) =>
    put(`/workflows/${enc(id)}/bindings`, WorkflowSchema, bindings),
  );

export const useCheckWorkflow = (id: string) =>
  useWorkflowMutation(() => post(`/workflows/${enc(id)}/check`, WorkflowSchema));

export const useCheckAllWorkflows = () =>
  useWorkflowMutation(() => post("/workflows/check-all", z.array(WorkflowSchema)));

/** The change list for the missing node packs and models (shown before anything installs). */
export const useDepsPlan = (id: string) =>
  useMutation({ mutationFn: () => post(`/workflows/${enc(id)}/deps`, DepsPlanSchema) });

const DepsInstalledSchema = z.object({
  workflow: WorkflowSchema,
  packs: z.number(),
  models: z.number(),
  /** The ComfyUI-Manager snapshot taken first. */
  snapshot: z.string(),
  /** A real ComfyUI loads new node packs when it restarts; the check shows them missing till then. */
  restart_required: z.boolean(),
  /** Packs that did not install: their name and why (a setup error code). */
  failed: z.array(z.object({ name: z.string(), code: z.string() })),
});

export const useInstallDeps = (id: string) =>
  useWorkflowMutation(() => post(`/workflows/${enc(id)}/deps/install`, DepsInstalledSchema));

export const useTrialWorkflow = (id: string) =>
  useWorkflowMutation(() => post(`/workflows/${enc(id)}/trial`, WorkflowSchema));

export type { Workflow };
