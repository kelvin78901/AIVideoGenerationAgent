import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, patch, post } from "@/api/client";
import { JobSchema } from "@/api/schemas/jobs";
import {
  ExportChecksSchema,
  TimelineSchema,
  type ClipPatch,
  type ExportFormat,
  type Timeline,
} from "@/api/schemas/timeline";

const enc = encodeURIComponent;

export const postKeys = {
  timeline: (episodeId: string) => ["episodes", episodeId, "timeline"] as const,
  checks: (episodeId: string) => ["episodes", episodeId, "export-checks"] as const,
};

export function useTimeline(episodeId: string | undefined) {
  return useQuery({
    queryKey: postKeys.timeline(episodeId ?? ""),
    queryFn: () => api(`/episodes/${enc(episodeId ?? "")}/timeline`, TimelineSchema),
    enabled: !!episodeId,
  });
}

export function useExportChecks(episodeId: string | undefined) {
  return useQuery({
    queryKey: postKeys.checks(episodeId ?? ""),
    queryFn: () => api(`/episodes/${enc(episodeId ?? "")}/export/checks`, ExportChecksSchema),
    enabled: !!episodeId,
  });
}

/** Clip settings; the timeline in the cache changes at once (sliders feel immediate). */
export function usePatchClip(episodeId: string | undefined) {
  const client = useQueryClient();
  const key = postKeys.timeline(episodeId ?? "");
  return useMutation({
    mutationFn: (p: { id: string; patch: ClipPatch }) =>
      patch(`/clips/${enc(p.id)}`, TimelineSchema, p.patch),
    onMutate: ({ id, patch: change }) =>
      client.setQueryData<Timeline>(
        key,
        (old) =>
          old && { ...old, clips: old.clips.map((c) => (c.id === id ? { ...c, ...change } : c)) },
      ),
    onSuccess: (timeline) => client.setQueryData(key, timeline),
    onError: () => client.invalidateQueries({ queryKey: key }),
  });
}

/**
 * Subtitle text. `draft` shows the text in the cache while typing (preview and timeline follow
 * as you type); `save` writes it.
 */
export function useSubtitleText(episodeId: string | undefined) {
  const client = useQueryClient();
  const key = postKeys.timeline(episodeId ?? "");
  const save = useMutation({
    mutationFn: (p: { id: string; text: string }) =>
      patch(`/subtitles/${enc(p.id)}`, TimelineSchema, { text: p.text }),
    onSuccess: (timeline) => client.setQueryData(key, timeline),
    onError: () => client.invalidateQueries({ queryKey: key }),
  });
  const draft = (id: string, text: string) =>
    client.setQueryData<Timeline>(
      key,
      (old) =>
        old && {
          ...old,
          subtitles: old.subtitles.map((s) => (s.id === id ? { ...s, text } : s)),
        },
    );
  return { draft, save };
}

export function useExport(episodeId: string | undefined) {
  return useMutation({
    mutationFn: (format: ExportFormat) =>
      post(`/episodes/${enc(episodeId ?? "")}/export`, JobSchema, { format }),
  });
}
