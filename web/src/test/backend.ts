import { http, HttpResponse } from "msw";

import { SeriesCreateSchema, type Series } from "@/api/schemas/series";
import {
  AspectSchema,
  SpecPatchSchema,
  type Aspect,
  type CompatRow,
  type OutputSpec,
  type SpecPresets,
} from "@/api/schemas/spec";
import { series as demoSeries } from "@/mocks/fixtures/demo/series";
import { spec as demoSpec } from "@/mocks/fixtures/demo/spec";
import { setBackendFetch } from "@/mocks/backend";
import { server } from "@/mocks/node";
import { assetHandlers, assetsBackendFetch, resetFakeAssets } from "@/test/fakes/assets";
import { bibleBackendFetch, bibleHandlers, resetFakeBible } from "@/test/fakes/bible";
import { dubHandlers, resetFakeDub } from "@/test/fakes/dub";
import { configHandlers, resetFakeConfig } from "@/test/fakes/config";
import { episodeHandlers, episodesBackendFetch, resetFakeEpisodes } from "@/test/fakes/episodes";
import { gateHandlers, impactBackendFetch, resetFakeImpact } from "@/test/fakes/impact";
import { novelHandlers, resetFakeNovel } from "@/test/fakes/novel";
import { resetFakeScript, scriptBackendFetch, scriptHandlers } from "@/test/fakes/script";
import { resetFakeSuggestions, suggestionHandlers } from "@/test/fakes/suggestions";
import { resetFakeSetup, setupHandlers } from "@/test/setupBackend";

type Dims = { w: number; h: number };
const even = (n: number) => Math.round(n / 2) * 2;
const RATIO: Record<Aspect, [number, number]> = {
  "9:16": [9, 16],
  "16:9": [16, 9],
  "3:4": [3, 4],
  "1:1": [1, 1],
  "21:9": [21, 9],
};

/** Test copy of `spec/dims.py` (the backend is the only place that computes sizes for real). */
function dimsOf(aspect: Aspect): { "1080p": Dims; "2k": Dims; draft: Dims } {
  const tier = (short: number): Dims => {
    const [w, h] = RATIO[aspect];
    return w <= h ? { w: short, h: even((short * h) / w) } : { w: even((short * w) / h), h: short };
  };
  const twoK = aspect === "21:9" ? { w: 2976, h: 1248 } : tier(1440);
  return { "1080p": tier(1080), "2k": twoK, draft: tier(768) };
}

const presets: SpecPresets = {
  platforms: [
    { id: "cn", aspect: "9:16", delivery: "1080p" },
    { id: "intl", aspect: "9:16", delivery: "1080p" },
    { id: "wide", aspect: "16:9", delivery: "1080p" },
    { id: "custom", aspect: null, delivery: null },
  ],
  dims: Object.fromEntries(AspectSchema.options.map((a) => [a, dimsOf(a)])) as SpecPresets["dims"],
};

/** `spec/compat.py`'s table for the default route (tests/unit/test_compat.py). */
function compatRows(aspect: Aspect): CompatRow[] {
  const is21 = aspect === "21:9";
  const row = (stage: string, keys: string[], status: CompatRow["status"], code: string) => ({
    stage,
    model_keys: keys,
    status,
    how: { code, params: {} },
  });
  return [
    row(
      "keyframe",
      ["google/nano-banana-pro"],
      is21 ? "unsupported" : "native",
      is21 ? "outpaint_from_16_9" : "native_4k",
    ),
    row("text_keyframe", ["openai/gpt-image-2"], "convert", "upscale_from_1k"),
    row("sketch", ["volc/seedream-5.0"], "native", "cheap_sketch"),
    row("video_draft", ["comfy/h3"], "native", "h3_aspects"),
    row("video_final", ["minimax/h3-regenerate-2k"], "native", "follow_draft"),
    row("video_alt", ["volc/seedance-2.5"], "convert", "upscale_from_720p"),
    row("upscale", ["comfy/seedvr2", "comfy/flashvsr"], "native", "any_aspect"),
  ];
}

/**
 * State of the fake backend; reset by every `backend()` call. Tests read and change it.
 * `series` is the demo series; `created` the ones made with `POST /series` (newest last), each
 * with the default spec in `specs`.
 */
export const fake: {
  series: Series;
  spec: OutputSpec;
  created: Series[];
  specs: Record<string, OutputSpec>;
} = {
  series: structuredClone(demoSeries),
  spec: structuredClone(demoSpec),
  created: [],
  specs: {},
};

const known = (id: unknown) => id === fake.series.id || fake.created.some((s) => s.id === id);
const seriesOf = (id: unknown) =>
  id === fake.series.id ? fake.series : fake.created.find((s) => s.id === id);
const specOf = (id: unknown) => (id === fake.series.id ? fake.spec : fake.specs[String(id)]);

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

function seriesHandlers() {
  return [
    http.get("*/api/v1/series", () =>
      HttpResponse.json([...fake.created].reverse().concat(fake.series)),
    ),
    http.post("*/api/v1/series", async ({ request }) => {
      const body = SeriesCreateSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const id = `s${fake.created.length + 1}`;
      const created: Series = {
        id,
        slug: id,
        title: body.data.title,
        ui_lang: body.data.ui_lang ?? "zh-CN",
        created_at: "2026-10-19T10:00:00Z",
      };
      fake.created.push(created);
      fake.specs[id] = { ...structuredClone(demoSpec), series_id: id, locked_at: null };
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get("*/api/v1/series/:id", ({ params }) => {
      const s = seriesOf(params.id);
      return s ? HttpResponse.json(s) : error(404, "series_not_found");
    }),
    http.get("*/api/v1/series/:id/spec", ({ params }) =>
      known(params.id) ? HttpResponse.json(specOf(params.id)) : error(404, "series_not_found"),
    ),
    // Series other than the demo have no products yet (the demo's are MSW's and the backend's).
    http.get("*/api/v1/products", ({ request }) => {
      const owner = new URL(request.url).searchParams.get("owner") ?? "";
      const [kind, id] = owner.split(":");
      return kind === "series" && id !== fake.series.id && known(id)
        ? HttpResponse.json([])
        : undefined;
    }),
    http.put("*/api/v1/series/:id/spec", async ({ params, request }) => {
      if (!known(params.id)) return error(404, "series_not_found");
      const body = SpecPatchSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const spec = specOf(params.id);
      if (!spec) return error(404, "series_not_found");
      const confirmed = new URL(request.url).searchParams.get("confirmed_impact");
      if (spec.locked_at && body.data.aspect && body.data.aspect !== spec.aspect && !confirmed)
        return error(409, "spec_locked", { aspect: spec.aspect });
      Object.assign(spec, body.data);
      const d = dimsOf(spec.aspect);
      spec.dims = { delivery: d[spec.delivery], draft: d.draft };
      return HttpResponse.json(spec);
    }),
    http.get("*/api/v1/series/:id/spec/compat", ({ params, request }) => {
      if (!known(params.id)) return error(404, "series_not_found");
      const q = AspectSchema.safeParse(new URL(request.url).searchParams.get("aspect"));
      const aspect = q.success ? q.data : (specOf(params.id)?.aspect ?? "9:16");
      return HttpResponse.json({ aspect, rows: compatRows(aspect) });
    }),
    http.get("*/api/v1/spec/presets", () => HttpResponse.json(presets)),
    ...novelHandlers(known),
    ...bibleHandlers(known),
    ...suggestionHandlers(known),
    ...episodeHandlers(known),
    ...scriptHandlers(),
    ...assetHandlers(),
    ...dubHandlers(),
    ...gateHandlers(),
  ];
}

/**
 * What the MSW demo merges in from the backend (`mocks/backend.ts`): products, the plan, and
 * the impact previews it lays its downstream over.
 */
async function fakeBackendFetch(request: Request): Promise<Response> {
  const url = new URL(request.url);
  return (
    (await impactBackendFetch(request)) ??
    bibleBackendFetch(url) ??
    episodesBackendFetch(url) ??
    scriptBackendFetch(url) ??
    assetsBackendFetch(url) ??
    HttpResponse.json({ detail: { code: "http_404", params: {} } }, { status: 404 })
  );
}

/**
 * Real backend endpoints pages read: live mode, DeepSeek without a key, an empty job list, the
 * series list with the demo series and its output spec, novel (`test/fakes/novel.ts`), bible
 * with its products (`test/fakes/bible.ts`), suggestions (`test/fakes/suggestions.ts`), the
 * episode plan (`test/fakes/episodes.ts`), each episode's script (`test/fakes/script.ts`),
 * episode 1's assets (`test/fakes/assets.ts`) and 台词配音 (`test/fakes/dub.ts`), the novel and script gates and impact previews
 * (`test/fakes/impact.ts`), and the PC sample machine
 * before its first scan
 * (`test/setupBackend.ts`, `fakeSetup`).
 */
export function backend({ mock = true }: { mock?: boolean } = {}) {
  fake.series = structuredClone(demoSeries);
  fake.spec = structuredClone(demoSpec);
  fake.created = [];
  fake.specs = {};
  resetFakeNovel();
  resetFakeBible();
  resetFakeSuggestions();
  resetFakeEpisodes();
  resetFakeScript();
  resetFakeAssets();
  resetFakeDub();
  resetFakeImpact();
  setBackendFetch(fakeBackendFetch);
  resetFakeSetup();
  resetFakeConfig();
  server.use(
    http.get("*/api/v1/health", () => HttpResponse.json({ status: "ok", version: "0", mock })),
    http.get("*/api/v1/jobs", () => HttpResponse.json([])),
    ...seriesHandlers(),
    ...setupHandlers(),
    ...configHandlers(),
    http.get("*/api/v1/providers", () =>
      HttpResponse.json({
        providers: [
          {
            id: "deepseek",
            name: "DeepSeek",
            where: "api",
            base_url: null,
            docs: null,
            verify: true,
            needs_key: true,
            has_key: false,
            key_source: "none",
            enabled: true,
            models: [
              {
                key: "deepseek/v4-pro",
                display: "x",
                model_id: null,
                price: null,
                json_mode: true,
              },
            ],
          },
        ],
        llm_ui_order: [],
      }),
    ),
  );
}
