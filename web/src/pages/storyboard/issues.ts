import { useShotChecks } from "@/api/hooks/shots";

/** How many 分镜检查 findings each shot has (the shot cards' badge; M5.5). */
export function useIssueCounts(episodeId: string | undefined): Record<string, number> {
  const checks = useShotChecks(episodeId);
  const counts: Record<string, number> = {};
  for (const i of checks.data?.issues ?? []) counts[i.shot_id] = (counts[i.shot_id] ?? 0) + 1;
  return counts;
}
