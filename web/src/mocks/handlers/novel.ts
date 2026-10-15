import { http } from "msw";

import type { Suggestion } from "@/api/schemas/novel";
import { getDb } from "@/mocks/db";
import { primaryModel } from "@/mocks/fixtures/demo/config";
import { suggestionRewrites } from "@/mocks/fixtures/demo/novel";
import { resolveConfig } from "@/mocks/handlers/config";
import { demoError, demoJson, v1 } from "@/mocks/http";

const seriesGuard = (id: string) =>
  getDb().series[id] ? null : demoError(404, "series_not_found", { id });

function findSuggestion(id: string): Suggestion | undefined {
  return getDb().suggestions.find((s) => s.id === id);
}

/** accept / reject / reset: the decision on one suggestion (reset = back to undecided). */
function decide(action: "accept" | "reject" | "reset") {
  return http.post(v1(`/suggestions/:id/${action}`), ({ params }) => {
    const s = findSuggestion(String(params.id));
    if (!s) return demoError(404, "suggestion_not_found", { id: params.id });
    s.status =
      action === "accept"
        ? "accepted"
        : action === "reject"
          ? "rejected"
          : s.rewrite_instruction
            ? "rewritten"
            : "pending";
    return demoJson(s);
  });
}

export const novelHandlers = [
  http.get(v1("/series/:id/novel"), ({ params }) => {
    const id = String(params.id);
    return seriesGuard(id) ?? demoJson(getDb().novel);
  }),

  http.get(v1("/series/:id/suggestions"), ({ params }) => {
    const id = String(params.id);
    return seriesGuard(id) ?? demoJson(getDb().suggestions.filter((s) => s.series_id === id));
  }),

  http.get(v1("/series/:id/bible"), ({ params }) => {
    const id = String(params.id);
    return seriesGuard(id) ?? demoJson(getDb().bible.filter((e) => e.series_id === id));
  }),

  // 「全部采纳」: every suggestion that was not ignored.
  http.post(v1("/series/:id/suggestions/accept-all"), ({ params }) => {
    const id = String(params.id);
    const missing = seriesGuard(id);
    if (missing) return missing;
    const list = getDb().suggestions.filter((s) => s.series_id === id);
    for (const s of list) if (s.status !== "rejected") s.status = "accepted";
    return demoJson(list);
  }),

  decide("accept"),
  decide("reject"),
  decide("reset"),

  // 「按要求重写这一条」 with the enrich component's current route.
  http.post(v1("/suggestions/:id/rewrite"), async ({ params, request }) => {
    const s = findSuggestion(String(params.id));
    if (!s) return demoError(404, "suggestion_not_found", { id: params.id });
    const body = (await request.json()) as { instruction?: unknown };
    const instruction = typeof body.instruction === "string" ? body.instruction.trim() : "";
    const cfg = resolveConfig("enrich", null);
    s.text = suggestionRewrites[s.id] ?? s.text;
    s.rewrite_instruction = instruction;
    s.rewritten_by = (cfg && primaryModel(cfg.values)) ?? null;
    if (s.status !== "accepted") s.status = "rewritten";
    return demoJson(s);
  }),
];
