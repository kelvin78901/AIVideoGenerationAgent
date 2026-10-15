/** Reading video takes (slot=video versions) the same way on the candidate wall and elsewhere. */
import type { Product, ProductVersion, QaCheck } from "@/api/schemas/products";
import type { Shot } from "@/api/schemas/shots";

/** Shot pill status on the generate page (prototype `statusOf`). */
export type TakeStatus = "adopted" | "picking" | "running" | "queued" | "waiting" | "not_started";

export function takeStatus(
  shot: Shot,
  product: Product | undefined,
  byLabel: (label: string) => Product | undefined,
): TakeStatus {
  if (product?.adopted_version_id) return "adopted";
  if (product?.versions.length) return "picking";
  if (product?.status === "running") return "running";
  if (product?.status === "queued") return "queued";
  if (shot.tail_from && !byLabel(shot.tail_from)?.adopted_version_id) return "waiting";
  return "not_started";
}

export function qaFails(v: ProductVersion): QaCheck[] {
  return v.qa?.checks.filter((c) => c.ok === false) ?? [];
}

/**
 * 推荐: the passing take with the highest QA score, later takes winning ties (SPEC 4.2).
 * None once a take is adopted.
 */
export function recommendedTake(product: Product): ProductVersion | undefined {
  if (product.adopted_version_id) return undefined;
  let best: ProductVersion | undefined;
  for (const v of product.versions) {
    if (v.qa_pass !== true || !v.qa) continue;
    if (!best || (best.qa && v.qa.score >= best.qa.score)) best = v;
  }
  return best;
}

/** Why the take exists, when it is worth saying (`generate:note.<key>`); null for plain runs. */
export type TakeNote =
  | "switch"
  | "auto_rerun"
  | "rerun_after_fail"
  | "hybrid_final"
  | "fallback_error"
  | "fallback_timeout"
  | "fallback_qa_fail";

export function takeNote(product: Product, v: ProductVersion): TakeNote | null {
  if (v.origin === "switch") return "switch";
  if (v.origin === "fallback") return `fallback_${v.fallback_reason ?? "error"}`;
  if (v.origin === "auto_qa_rerun") return "auto_rerun";
  if (v.stage === "final") return "hybrid_final";
  const rerun = product.versions.some(
    (c) => c.parent_version_id === v.id && c.origin === "auto_qa_rerun",
  );
  return v.qa_pass === false && rerun ? "rerun_after_fail" : null;
}

/** The shot that starts from this shot's last frame and was waiting for it (「下游镜头」). */
export function waitingDownstream(shots: Shot[], label: string): Shot | undefined {
  return shots.find((s) => s.tail_from === label);
}
