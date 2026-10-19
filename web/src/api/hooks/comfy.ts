/** The user's own ComfyUI (SPEC 6.4.1): what the scan identified, snapshots and rollback. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, post } from "@/api/client";
import { ComfySnapshotSchema, ComfyViewSchema, RestoredSchema } from "@/api/schemas/comfy";

const enc = encodeURIComponent;

export const comfyKeys = {
  all: ["comfy"] as const,
  env: ["comfy", "env"] as const,
  snapshots: ["comfy", "snapshots"] as const,
};

/** As of the last finished scan; a rescan refreshes it (`applySetupProgress`). */
export function useComfyEnv() {
  return useQuery({
    queryKey: comfyKeys.env,
    queryFn: () => api("/comfy/env", ComfyViewSchema),
  });
}

/** Newest first. */
export function useComfySnapshots({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: comfyKeys.snapshots,
    queryFn: () => api("/comfy/snapshots", z.array(ComfySnapshotSchema)),
    enabled,
  });
}

function useSnapshotMutation<V, R>(fn: (vars: V) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => client.invalidateQueries({ queryKey: comfyKeys.snapshots }),
  });
}

/** 「现在存一份」: a manual ComfyUI-Manager snapshot. */
export const useTakeSnapshot = () =>
  useSnapshotMutation(() => post("/comfy/snapshots", ComfySnapshotSchema));

/** Applied by ComfyUI-Manager when the user restarts ComfyUI (`restart_required`). */
export const useRestoreSnapshot = () =>
  useSnapshotMutation((id: string) => post(`/comfy/snapshots/${enc(id)}/restore`, RestoredSchema));
