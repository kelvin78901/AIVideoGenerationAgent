import type { TFunction } from "i18next";

import { SELECT_CONDITIONS, type SelectWhen } from "@/api/schemas/generate";

/** The rules table's anchor on the models page (the Inspector links to it). */
export const WORKFLOW_RULES_ANCHOR = "workflow-rules";

/** A rule's conditions as one line (特写 · 有台词); no condition = every shot. */
export function describeWhen(
  t: TFunction<"models">,
  te: TFunction<"enums">,
  when: SelectWhen,
): string {
  const parts = SELECT_CONDITIONS.flatMap((cond) => {
    const value = when[cond];
    if (value === undefined) return [];
    switch (cond) {
      case "framing":
        return [te(`framing.${when.framing ?? "wide"}`)];
      case "shot_type":
        return [te(`shotType.${when.shot_type ?? "continuous"}`)];
      case "audio_mode":
        return [te(`audioMode.${when.audio_mode ?? "none"}`)];
      default:
        return [t(`wfRules.flag.${cond}.${value ? "true" : "false"}`)];
    }
  });
  return parts.length ? parts.join(" · ") : t("wfRules.anyShot");
}
