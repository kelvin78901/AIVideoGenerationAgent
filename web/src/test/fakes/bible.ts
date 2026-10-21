/**
 * Fake story bible for page tests: the demo series' bible and its backend products (the novel,
 * 设定提取) as the Mock backend answers them (`test/data/bible.json`, written by
 * tests/api/test_web_fixtures.py). Edits follow the backend's rules closely enough for the page
 * (`bible/merge.py`): a new name keeps the old one as an alias, a merge keeps the first entry,
 * 「不是同一个」 drops the suggestion, a split makes the alias an entry of its own.
 */
import { http, HttpResponse } from "msw";

import {
  BibleSchema,
  type Bible,
  type BibleEntity,
  type BibleMergeRequest,
  type BiblePatch,
} from "@/api/schemas/novel";
import { ProductSchema, type Product } from "@/api/schemas/products";
import { modelByKey } from "@/mocks/fixtures/demo/models";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import { primaryModel } from "@/mocks/route";
import data from "@/test/data/bible.json";
import { fakeResolve } from "@/test/fakes/config";

const demoBible = BibleSchema.parse(data.bible);
const demoProducts = data.products.map((p) => ProductSchema.parse(p));

/** State of the fake; `resetFakeBible()` (called by `backend()`) restores it. */
export const fakeBible = {
  bible: structuredClone(demoBible),
  products: structuredClone(demoProducts),
  /** Every edit sent, in order. */
  edits: [] as (({ id: string } & BiblePatch) | BibleMergeRequest)[],
};

export function resetFakeBible() {
  fakeBible.bible = structuredClone(demoBible);
  fakeBible.products = structuredClone(demoProducts);
  fakeBible.edits = [];
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

const empty = (series: string): Bible => ({
  series_id: series,
  product_id: null,
  version_id: null,
  adopted: true,
  source_id: null,
  entities: [],
  merge_suggestions: [],
});

const find = (id: string) => fakeBible.bible.entities.find((e) => e.id === id);

function unique(names: string[], exclude: string): string[] {
  return [...new Set(names.map((n) => n.trim()).filter((n) => n && n !== exclude))];
}

function merge(ids: string[]): Response | null {
  const [keep, ...others] = ids.map(find);
  if (!keep || others.some((o) => !o)) return error(404, "entity_not_found");
  const gone = others as BibleEntity[];
  keep.aliases = unique(
    [...keep.aliases, ...gone.flatMap((o) => [o.name, ...o.aliases])],
    keep.name,
  );
  keep.paras = [...new Set([...keep.paras, ...gone.flatMap((o) => o.paras)])].sort((a, b) => a - b);
  const bible = fakeBible.bible;
  bible.entities = bible.entities.filter((e) => !gone.includes(e));
  bible.merge_suggestions = bible.merge_suggestions.filter(
    (s) => !s.ids.some((id) => gone.some((o) => o.id === id)),
  );
  return null;
}

/**
 * The next run's estimate follows the component's route, as the backend computes it on read
 * (another model of the same kind keeps the exported price; a local one costs nothing).
 */
function withRoute(p: Product): Product {
  const model = primaryModel(fakeResolve(p.component_id, null)?.values ?? null);
  if (!p.estimate || !model || model === p.estimate.model_key) return p;
  const where = modelByKey(model)?.where ?? "api";
  const cost_usd = where === "local" ? 0 : p.estimate.cost_usd;
  return { ...p, estimate: { ...p.estimate, model_key: model, where, cost_usd } };
}

/** The fake backend's products of the demo series, which the MSW demo merges in, or null. */
export function bibleBackendFetch(url: URL): Response | null {
  if (url.pathname.endsWith("/products") && url.searchParams.get("owner") === "series:demo")
    return HttpResponse.json(fakeBible.products.map(withRoute));
  return null;
}

/** `known`: the series the fake backend has. */
export function bibleHandlers(known: (id: string) => boolean) {
  return [
    http.get("*/api/v1/series/:id/bible", ({ params }) => {
      const id = String(params.id);
      if (!known(id)) return error(404, "series_not_found", { id });
      return HttpResponse.json(id === DEMO_SERIES_ID ? fakeBible.bible : empty(id));
    }),

    http.patch("*/api/v1/bible/:id", async ({ params, request }) => {
      const id = String(params.id);
      const e = find(id);
      if (!e) return error(404, "entity_not_found", { id });
      const body = (await request.json()) as BiblePatch;
      fakeBible.edits.push({ id, ...body });
      if (body.name !== undefined) {
        if (!body.name.trim()) return error(422, "name_required");
        const old = e.name;
        e.name = body.name.trim();
        e.aliases = unique(body.aliases ?? [...e.aliases, old], e.name);
      } else if (body.aliases) e.aliases = unique(body.aliases, e.name);
      if (body.data) e.data = { ...body.data, summary: String(body.data.summary ?? "") };
      if (body.frozen !== undefined) e.frozen = body.frozen;
      return HttpResponse.json(e);
    }),

    http.post("*/api/v1/bible/merge", async ({ request }) => {
      const body = (await request.json()) as BibleMergeRequest;
      fakeBible.edits.push(body);
      const bible = fakeBible.bible;
      if (body.action === "split") {
        const e = find(body.ids[0]);
        if (!e || !e.aliases.includes(body.alias))
          return error(422, "alias_not_found", { alias: body.alias });
        e.aliases = e.aliases.filter((a) => a !== body.alias);
        const fresh: BibleEntity = {
          ...structuredClone(e),
          id: `${e.id}-split`,
          name: body.alias,
          aliases: [],
          data: { summary: "" },
          frozen: false,
        };
        bible.entities.splice(bible.entities.indexOf(e) + 1, 0, fresh);
      } else if (body.action === "merge") {
        const failed = merge(body.ids);
        if (failed) return failed;
      } else {
        bible.merge_suggestions = bible.merge_suggestions.filter(
          (s) => !body.ids.every((id) => s.ids.includes(id)),
        );
      }
      return HttpResponse.json(bible);
    }),

    http.get("*/api/v1/products/:id", ({ params }) => {
      const p = fakeBible.products.find((x: Product) => x.id === params.id);
      return p ? HttpResponse.json(withRoute(p)) : undefined;
    }),
  ];
}
