import { useMutation, useQueryClient } from "@tanstack/react-query";

import { post } from "@/api/client";
import { seriesKeys } from "@/api/hooks/series";
import { GateDecisionSchema, type Gate } from "@/api/schemas/gates";

/**
 * 「确认……，进入下一步」 / 重新打开. `scopeId` is the series for the novel gate (it shows on
 * every episode, and there may be none yet), else the episode.
 */
export function useGate(gate: Gate, scopeId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: "confirm" | "reopen") =>
      post(`/gates/${gate}/${action}`, GateDecisionSchema, { scope_id: scopeId }),
    onSuccess: () =>
      gate === "novel"
        ? Promise.all([
            client.invalidateQueries({ queryKey: seriesKeys.seriesProgress(scopeId) }),
            client.invalidateQueries({
              predicate: (q) => q.queryKey[0] === "episodes" && q.queryKey[2] === "progress",
            }),
          ])
        : client.invalidateQueries({ queryKey: seriesKeys.progress(scopeId) }),
  });
}
