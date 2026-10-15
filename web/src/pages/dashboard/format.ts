/** Wording helpers for the dashboard: server messages (code + params), durations, time ranges. */
import { useTranslation } from "react-i18next";

import type { Message } from "@/api/schemas/common";
import { formatTime, formatUsd } from "@/lib/format";

/** Params that carry USD amounts; they are formatted "$3.04". */
const MONEY = new Set(["cost", "voice", "images", "price"]);

export type MessagePrefix =
  | "insight"
  | "spend.item"
  | "shots.note"
  | "shots.take"
  | "speed.note"
  | "apis.usage"
  | "apis.note"
  | "local.note";

/**
 * Renders `dashboard.<prefix>.<code>`. `component*` params are components.yaml ids and are
 * translated through `enums:component`; `issues` is a comma list of QA issue codes
 * (`enums:qaIssue`); money params are formatted as USD.
 */
export function useDashboardMessage() {
  const { t } = useTranslation("dashboard");
  const { t: te } = useTranslation("enums");
  return (prefix: MessagePrefix, m: Message): string => {
    const params = Object.fromEntries(
      Object.entries(m.params).map(([k, v]) => {
        if (k.startsWith("component") && typeof v === "string")
          return [k, te(`component.${v}` as "component.enrich", { defaultValue: v })];
        if (k === "issues" && typeof v === "string")
          return [
            k,
            v
              .split(",")
              .map((c) => te(`qaIssue.${c}` as "qaIssue.face_mismatch", { defaultValue: c }))
              .join(t("listSep")),
          ];
        if (MONEY.has(k) && typeof v === "number") return [k, formatUsd(v, { cents: true })];
        return [k, v];
      }),
    );
    return t(`${prefix}.${m.code}` as "insight.one_off_assets", {
      ...params,
      defaultValue: m.code,
    });
  };
}

/** "2 小时 12 分" / "44 分钟". */
export function useDuration() {
  const { t } = useTranslation("dashboard");
  return (seconds: number): string => {
    const minutes = Math.round(seconds / 60);
    const h = Math.floor(minutes / 60);
    return h > 0 ? t("duration.hm", { h, m: minutes % 60 }) : t("duration.m", { m: minutes });
  };
}

/** "11:45–11:55". */
export const timeRange = (start: string, end: string) => `${formatTime(start)}–${formatTime(end)}`;

/** Minutes between two ISO timestamps. */
export const minutesBetween = (from: string, to: string) =>
  (new Date(to).getTime() - new Date(from).getTime()) / 60000;
