import { useMutation, useQuery } from "@tanstack/react-query";

import { api, post } from "@/api/client";
import { RewriteProposalSchema, ScriptSchema } from "@/api/schemas/script";

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

/** 「重写这一段」 / 「换模型重写」: a proposal; saving goes through the impact preview. */
export function useRewriteBlock() {
  return useMutation({
    mutationFn: (b: { id: string; scene: boolean; model?: string }) =>
      post(`/${b.scene ? "scenes" : "lines"}/${enc(b.id)}/rewrite`, RewriteProposalSchema, {
        model: b.model,
      }),
  });
}
