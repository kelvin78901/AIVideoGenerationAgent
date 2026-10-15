/** Sync to external tools (SPEC 14): settings, detection, manual run, log, ComfyUI board. */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, post, put } from "@/api/client";
import {
  SyncBoardSchema,
  SyncLogEntrySchema,
  SyncRunSchema,
  SyncSettingsSchema,
  SyncTargetSchema,
  type SyncRun,
  type SyncSettings,
  type SyncSettingsPatch,
  type SyncTargetId,
} from "@/api/schemas/sync";

const enc = encodeURIComponent;

export const syncKeys = {
  settings: ["sync", "settings"] as const,
  log: ["sync", "log"] as const,
  board: (episodeId: string) => ["sync", "board", episodeId] as const,
  /** The manual run in progress; only written by `POST /sync/run` and `sync.updated`. */
  run: ["sync", "run"] as const,
};

export function useSyncSettings() {
  return useQuery({
    queryKey: syncKeys.settings,
    queryFn: () => api("/sync/targets", SyncSettingsSchema),
  });
}

export function useSaveSyncSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: SyncSettingsPatch) => put("/sync/targets", SyncSettingsSchema, patch),
    onSuccess: (s) => client.setQueryData(syncKeys.settings, s),
  });
}

/** 「重新检测」 one target; the card shows what detection found this time. */
export function useDetectTarget() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: SyncTargetId) => post(`/sync/targets/${enc(id)}/detect`, SyncTargetSchema),
    onSuccess: (target) =>
      client.setQueryData<SyncSettings>(syncKeys.settings, (s) =>
        s ? { ...s, targets: s.targets.map((x) => (x.id === target.id ? target : x)) } : s,
      ),
  });
}

export function useSyncLog(seriesId: string) {
  return useQuery({
    queryKey: syncKeys.log,
    queryFn: () => api(`/sync/log?series=${enc(seriesId)}`, z.array(SyncLogEntrySchema)),
  });
}

export function useSyncBoard(episodeId: string | undefined) {
  return useQuery({
    queryKey: syncKeys.board(episodeId ?? ""),
    queryFn: () => api(`/sync/board?episode=${enc(episodeId ?? "")}`, SyncBoardSchema),
    enabled: !!episodeId,
  });
}

/** Progress of the manual run (null when none has started in this session). */
export function useSyncRun() {
  return useQuery<SyncRun | null>({
    queryKey: syncKeys.run,
    queryFn: () => null,
    staleTime: Infinity,
  });
}

export function useStartSync() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (episodeId: string) => post("/sync/run", SyncRunSchema, { episode_id: episodeId }),
    onSuccess: (run) =>
      client.setQueryData<SyncRun | null>(syncKeys.run, (cur) =>
        // An event may already have moved this run further.
        cur?.run_id === run.run_id && cur.done > run.done ? cur : run,
      ),
  });
}

/** `sync.updated`: progress of a run; a finished run adds a line to the log. */
export function applySyncUpdate(client: QueryClient, run: SyncRun): void {
  client.setQueryData(syncKeys.run, run);
  if (run.state !== "running") void client.invalidateQueries({ queryKey: syncKeys.log });
}
