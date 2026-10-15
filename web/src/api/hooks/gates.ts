import { useMutation, useQueryClient } from "@tanstack/react-query";

import { post } from "@/api/client";
import { seriesKeys } from "@/api/hooks/series";
import { GateDecisionSchema, type Gate } from "@/api/schemas/gates";

/** 「确认……，进入下一步」 / 重新打开 for one episode. */
export function useGate(gate: Gate, episodeId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: "confirm" | "reopen") =>
      post(`/gates/${gate}/${action}`, GateDecisionSchema, { scope_id: episodeId }),
    onSuccess: () => client.invalidateQueries({ queryKey: seriesKeys.progress(episodeId) }),
  });
}
