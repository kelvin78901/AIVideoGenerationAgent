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

/** Polls while a trial runs (M5 moves this to job events). */
export function useWorkflows() {
  return useQuery({
    queryKey: workflowKeys.all,
    queryFn: () => api("/workflows", z.array(WorkflowSchema)),
    refetchInterval: (q) =>
      q.state.data?.some((w) => w.trial?.status === "running") ? 1000 : false,
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
});

export const useInstallDeps = (id: string) =>
  useWorkflowMutation(() => post(`/workflows/${enc(id)}/deps/install`, DepsInstalledSchema));

export const useTrialWorkflow = (id: string) =>
  useWorkflowMutation(() => post(`/workflows/${enc(id)}/trial`, WorkflowSchema));

export type { Workflow };
