import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, patch, post } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { seriesKeys } from "@/api/hooks/series";
import {
  RewriteProposalSchema,
  ScriptSchema,
  type BlockRewriteRequest,
} from "@/api/schemas/script";

const enc = encodeURIComponent;

export const scriptKeys = {
  script: (episodeId: string) => ["episodes", episodeId, "script"] as const,
};

export function useScript(episodeId: string | undefined) {
  return useQuery({
    queryKey: scriptKeys.script(episodeId ?? ""),
    queryFn: () => api(`/episodes/${enc(episodeId ?? "")}/script`, ScriptSchema),
    enabled: !!episodeId,
  });
}

/**
 * 改一行 / 改场景标题 of an unconfirmed script (`PATCH /lines|scenes/{id}`): the answer is the
 * whole script. A confirmed one goes through the impact preview instead.
 */
export function usePatchBlock(seriesId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (b: { id: string; scene: boolean; text: string }) =>
      b.scene
        ? patch(`/scenes/${enc(b.id)}`, ScriptSchema, { heading: b.text })
        : patch(`/lines/${enc(b.id)}`, ScriptSchema, { text: b.text }),
    onSuccess: (script) => {
      client.setQueryData(scriptKeys.script(script.episode_id), script);
      // A new version of 剧本化 (RunBar, history) and the episode's badges.
      void client.invalidateQueries({ queryKey: productKeys.all });
      void client.invalidateQueries({ queryKey: seriesKeys.episodes(seriesId) });
    },
  });
}

/**
 * 「重写这一段」 / 「换模型重写」: a proposal; keeping it is an edit. 409 `over_budget` until the
 * user agrees (`confirm_budget`).
 */
export function useRewriteBlock() {
  return useMutation({
    mutationFn: (b: { id: string; scene: boolean } & BlockRewriteRequest) => {
      const { id, scene, ...body } = b;
      return post(`/${scene ? "scenes" : "lines"}/${enc(id)}/rewrite`, RewriteProposalSchema, body);
    },
  });
}
