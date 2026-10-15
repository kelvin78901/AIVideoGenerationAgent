import { http } from "msw";

import {
  AspectSchema,
  SpecPatchSchema,
  type Aspect,
  type CompatRow,
  type OutputSpec,
  type SpecPresets,
} from "@/api/schemas/spec";
import { getDb } from "@/mocks/db";
import { demoError, demoJson, v1 } from "@/mocks/http";

type Dims = { w: number; h: number };
const even = (n: number) => Math.round(n / 2) * 2;

/** SPEC 13.1, as `spec/dims.py` will compute it: delivery tiers and the 768p draft tier. */
const RATIO: Record<Aspect, [number, number]> = {
  "9:16": [9, 16],
  "16:9": [16, 9],
  "3:4": [3, 4],
  "1:1": [1, 1],
  "21:9": [21, 9],
};

function tier(aspect: Aspect, short: number): Dims {
  const [w, h] = RATIO[aspect];
  return w <= h ? { w: short, h: even((short * h) / w) } : { w: even((short * w) / h), h: short };
}

export function dimsOf(aspect: Aspect): { "1080p": Dims; "2k": Dims; draft: Dims } {
  // 21:9 2K is capped by H3 at about 2976×1248.
  const twoK = aspect === "21:9" ? { w: 2976, h: 1248 } : tier(aspect, 1440);
  return { "1080p": tier(aspect, 1080), "2k": twoK, draft: tier(aspect, 768) };
}

export const presets: SpecPresets = {
  platforms: [
    { id: "cn", aspect: "9:16", delivery: "1080p" },
    { id: "intl", aspect: "9:16", delivery: "1080p" },
    { id: "wide", aspect: "16:9", delivery: "1080p" },
    { id: "custom", aspect: null, delivery: null },
  ],
  dims: Object.fromEntries(AspectSchema.options.map((a) => [a, dimsOf(a)])) as SpecPresets["dims"],
};

function withDims(spec: OutputSpec): OutputSpec {
  const d = dimsOf(spec.aspect);
  spec.dims = { delivery: d[spec.delivery], draft: d.draft };
  return spec;
}

/** Writes a spec change (from `PUT /spec`, or `/impact/apply` for the aspect). */
export function applySpecChange(seriesId: string, patch: Record<string, unknown>): void {
  const spec = getDb().specs[seriesId];
  const body = SpecPatchSchema.safeParse(patch);
  if (spec && body.success) withDims(Object.assign(spec, body.data));
}

/** The prototype's table: which models on the route make this aspect natively. */
function compatRows(aspect: Aspect): CompatRow[] {
  const is21 = aspect === "21:9";
  const row = (
    stage: string,
    model_keys: string[],
    status: CompatRow["status"],
    code: string,
  ): CompatRow => ({ stage, model_keys, status, how: { code, params: {} } });
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

export const specHandlers = [
  http.get(v1("/spec/presets"), () => demoJson(presets)),

  http.put(v1("/series/:id/spec"), async ({ params, request }) => {
    const spec = getDb().specs[String(params.id)];
    if (!spec) return demoError(404, "series_not_found", { id: params.id });
    const body = SpecPatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    // SPEC 13.3: once locked, a new aspect must go through the impact preview first.
    if (spec.locked_at && body.data.aspect && body.data.aspect !== spec.aspect)
      return demoError(409, "spec_locked", { aspect: spec.aspect });
    return demoJson(withDims(Object.assign(spec, body.data)));
  }),

  http.get(v1("/series/:id/spec/compat"), ({ params, request }) => {
    const spec = getDb().specs[String(params.id)];
    if (!spec) return demoError(404, "series_not_found", { id: params.id });
    const q = AspectSchema.safeParse(new URL(request.url).searchParams.get("aspect"));
    const aspect = q.success ? q.data : spec.aspect;
    return demoJson({ aspect, rows: compatRows(aspect) });
  }),
];
