import { http, HttpResponse } from "msw";

import type { Series } from "@/api/schemas/series";
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
import { server } from "@/mocks/node";
import { configHandlers, resetFakeConfig } from "@/test/fakes/config";
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

/** State of the fake backend; reset by every `backend()` call. Tests read and change it. */
export const fake: { series: Series; spec: OutputSpec } = {
  series: structuredClone(demoSeries),
  spec: structuredClone(demoSpec),
};

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

function seriesHandlers() {
  const known = (id: unknown) => id === fake.series.id;
  return [
    http.get("*/api/v1/series/:id", ({ params }) =>
      known(params.id) ? HttpResponse.json(fake.series) : error(404, "series_not_found"),
    ),
    http.get("*/api/v1/series/:id/spec", ({ params }) =>
      known(params.id) ? HttpResponse.json(fake.spec) : error(404, "series_not_found"),
    ),
    http.put("*/api/v1/series/:id/spec", async ({ params, request }) => {
      if (!known(params.id)) return error(404, "series_not_found");
      const body = SpecPatchSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const spec = fake.spec;
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
      const aspect = q.success ? q.data : fake.spec.aspect;
      return HttpResponse.json({ aspect, rows: compatRows(aspect) });
    }),
    http.get("*/api/v1/spec/presets", () => HttpResponse.json(presets)),
  ];
}

/**
 * Real backend endpoints pages read: live mode, DeepSeek without a key, an empty job list, the
 * demo series with its output spec, and the PC sample machine before its first scan
 * (`test/setupBackend.ts`, `fakeSetup`).
 */
export function backend({ mock = true }: { mock?: boolean } = {}) {
  fake.series = structuredClone(demoSeries);
  fake.spec = structuredClone(demoSpec);
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
