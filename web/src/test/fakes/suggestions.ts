/**
 * Fake 小说补全 suggestions for page tests: the demo series' suggestions as the Mock backend
 * answers them (`test/data/suggestions.json`, written by tests/api/test_web_fixtures.py).
 * Decisions follow the backend's rules (`suggestions/service.py`): no version is made, 「撤销」
 * after a rewrite goes back to 「已重写」, an accepted suggestion stays accepted when rewritten,
 * 「全部采纳」 skips the ignored ones. A rewrite returns the demo's rewrite on the route's model,
 * and answers 409 `over_budget` while `overBudget` is set and the user has not confirmed.
 */
import { http, HttpResponse } from "msw";

import { SuggestionsSchema, type Suggestion, type Suggestions } from "@/api/schemas/novel";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import { primaryModel } from "@/mocks/route";
import data from "@/test/data/suggestions.json";
import { fakeResolve } from "@/test/fakes/config";

const demo = SuggestionsSchema.parse(data.suggestions);
const rewrites: Record<string, string> = data.rewrites;

type Request =
  | { id: string; action: "accept" | "reject" | "reset" }
  | { id: string; action: "rewrite"; instruction: string; confirm_budget: boolean };

/** State of the fake; `resetFakeSuggestions()` (called by `backend()`) restores it. */
export const fakeSuggestions = {
  data: structuredClone(demo),
  /** Set to make a rewrite cost more than the per-call cap (until `confirm_budget`). */
  overBudget: null as { estimate_usd: number; limit_usd: number } | null,
  /** Every decision sent, in order. */
  requests: [] as Request[],
};

export function resetFakeSuggestions() {
  fakeSuggestions.data = structuredClone(demo);
  fakeSuggestions.overBudget = null;
  fakeSuggestions.requests = [];
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

const empty = (series: string): Suggestions => ({
  series_id: series,
  product_id: null,
  version_id: null,
  adopted: true,
  source_id: null,
  suggestions: [],
});

const find = (id: string): Suggestion | undefined =>
  fakeSuggestions.data.suggestions.find((s) => s.id === id);

/** `known`: the series the fake backend has. */
export function suggestionHandlers(known: (id: string) => boolean) {
  const list = (id: string) =>
    !known(id)
      ? error(404, "series_not_found", { id })
      : HttpResponse.json(id === DEMO_SERIES_ID ? fakeSuggestions.data : empty(id));

  return [
    http.get("*/api/v1/series/:id/suggestions", ({ params }) => list(String(params.id))),

    http.post("*/api/v1/series/:id/suggestions/accept-all", ({ params }) => {
      const id = String(params.id);
      if (id === DEMO_SERIES_ID)
        for (const s of fakeSuggestions.data.suggestions)
          if (s.status !== "rejected") s.status = "accepted";
      return list(id);
    }),

    http.post("*/api/v1/suggestions/:id/rewrite", async ({ params, request }) => {
      const s = find(String(params.id));
      if (!s) return error(404, "suggestion_not_found", { id: params.id });
      const body = (await request.json()) as { instruction: string; confirm_budget?: boolean };
      const confirm = body.confirm_budget ?? false;
      fakeSuggestions.requests.push({
        id: s.id,
        action: "rewrite",
        instruction: body.instruction,
        confirm_budget: confirm,
      });
      if (!body.instruction.trim()) return error(422, "instruction_required");
      if (fakeSuggestions.overBudget && !confirm)
        return error(409, "over_budget", fakeSuggestions.overBudget);
      s.text = rewrites[s.id] ?? `${s.text}（${body.instruction}）`;
      s.rewrite_instruction = body.instruction.trim();
      s.rewritten_by = primaryModel(fakeResolve("enrich", null)?.values ?? null);
      if (s.status !== "accepted") s.status = "rewritten";
      return HttpResponse.json(s);
    }),

    http.post("*/api/v1/suggestions/:id/:action", ({ params }) => {
      const action = String(params.action);
      if (action !== "accept" && action !== "reject" && action !== "reset")
        return error(422, "invalid_request");
      const s = find(String(params.id));
      if (!s) return error(404, "suggestion_not_found", { id: params.id });
      fakeSuggestions.requests.push({ id: s.id, action });
      s.status =
        action === "accept"
          ? "accepted"
          : action === "reject"
            ? "rejected"
            : s.rewrite_instruction
              ? "rewritten"
              : "pending";
      return HttpResponse.json(s);
    }),
  ];
}
