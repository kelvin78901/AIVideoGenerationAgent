/**
 * Fake picture sets for page tests (`pipeline/pictures.py`, M5.5): 镜头参考图 `shot_refs` (owner a
 * shot: composition / pose / light / style, at most 4; a continuous shot 409 `no_keyframe`) and
 * 风格板 `style_board` (owner the series: style, at most 4). Adding or removing a picture is a
 * new version with the rest renumbered, adopted at once; the set's product is made on its first
 * picture. A shot's products list (`?owner=shot:<id>`) is its keyframe and its set.
 */
import { http, HttpResponse } from "msw";

import type { Product, ProductVersion } from "@/api/schemas/products";
import { fakeShotProducts, findShot } from "@/test/fakes/shots";

const SETS = {
  shot_refs: { owner: "shot", purposes: ["composition", "pose", "light", "style"], max: 4 },
  style_board: { owner: "series", purposes: ["style"], max: 4 },
} as const;
type Slot = keyof typeof SETS;

/** State of the fake; `resetFakePictures()` (called by `backend()`) restores it. */
export const fakePictures = { products: [] as Product[] };

export function resetFakePictures() {
  fakePictures.products = [];
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

/** The picture sets of an owner (`shot:<id>`, `series:<id>`). */
export function fakePictureProducts(owner: string): Product[] {
  return fakePictures.products.filter((p) => `${p.owner_type}:${p.owner_id}` === owner);
}

function setOf(slot: Slot, ownerId: string): Product {
  const found = fakePictures.products.find((p) => p.slot === slot && p.owner_id === ownerId);
  if (found) return found;
  const p: Product = {
    id: `${slot}-${ownerId}`,
    series_id: "demo",
    owner_type: SETS[slot].owner,
    owner_id: ownerId,
    slot,
    component_id: "upload",
    current_version_id: null,
    adopted_version_id: null,
    locked_hash: null,
    status: "empty",
    versions: [],
    prompt: null,
    estimate: null,
    running: null,
  };
  fakePictures.products.push(p);
  return p;
}

const filesOf = (p: Product) =>
  p.versions.find((v) => v.id === p.adopted_version_id)?.files.filter((f) => f.role === "ref") ??
  [];

function append(p: Product, files: ProductVersion["files"], origin: "upload" | "edit"): Product {
  const n = p.versions.length + 1;
  const id = `${p.id}-v${n}`;
  p.versions.push({
    id,
    product_id: p.id,
    n,
    origin,
    parent_version_id: p.current_version_id,
    payload: { refs: files.map((f) => ({ purpose: f.purpose })) },
    files: files.map((f, i) => ({ ...f, idx: i })),
    content_hash: `sha256:${id}`,
    intent: null,
    compiled: null,
    compiled_overridden: false,
    model_key: null,
    where: null,
    seed: null,
    params: {},
    qa: null,
    qa_pass: null,
    fallback_reason: null,
    stage: null,
    rating: null,
    cost_usd: 0,
    job_id: null,
    created_at: "2026-11-13T10:00:00Z",
    note: null,
  });
  p.current_version_id = id;
  p.adopted_version_id = id;
  p.status = "ready";
  return p;
}

async function add(slot: Slot, ownerId: string, request: Request): Promise<Response> {
  const form = await request.formData();
  const file = form.get("file");
  if (!file || typeof file === "string") return error(422, "not_an_image");
  const purpose = String(form.get("purpose") ?? SETS[slot].purposes[0]);
  if (!(SETS[slot].purposes as readonly string[]).includes(purpose))
    return error(422, "invalid_purpose", { purpose });
  const p = setOf(slot, ownerId);
  const files = filesOf(p);
  if (files.length >= SETS[slot].max) return error(409, "too_many_refs", { limit: SETS[slot].max });
  const sha = `${p.id}-${p.versions.length + 1}-${file.name}`;
  const entry = {
    role: "ref",
    path: `blobs/sha256/00/${sha}`,
    sha256: sha,
    mime: file.type || "image/png",
    duration_s: null,
    w: 800,
    h: 600,
    idx: files.length,
    purpose,
  };
  return HttpResponse.json(append(p, [...files, entry], "upload"));
}

function remove(slot: Slot, ownerId: string, idx: number): Response {
  const p = fakePictures.products.find((x) => x.slot === slot && x.owner_id === ownerId);
  const files = p ? filesOf(p) : [];
  if (!p || !files[idx]) return error(404, "ref_not_found", { id: ownerId, idx });
  return HttpResponse.json(
    append(
      p,
      files.filter((_, i) => i !== idx),
      "edit",
    ),
  );
}

function shotOwner(id: unknown): Response | string {
  const s = findShot(id);
  if (!s) return error(404, "shot_not_found", { id });
  if (s.shot_type === "continuous") return error(409, "no_keyframe", { id: s.id });
  return s.id;
}

export function pictureHandlers() {
  return [
    http.get("*/api/v1/products", ({ request }) => {
      const owner = new URL(request.url).searchParams.get("owner") ?? "";
      if (!owner.startsWith("shot:")) return undefined;
      return HttpResponse.json([...fakeShotProducts(owner), ...fakePictureProducts(owner)]);
    }),
    http.get("*/api/v1/products/:id", ({ params }) => {
      const p = fakePictures.products.find((x) => x.id === params.id);
      return p ? HttpResponse.json(p) : undefined;
    }),
    http.post("*/api/v1/shots/:id/refs", ({ params, request }) => {
      const id = shotOwner(params.id);
      return typeof id === "string" ? add("shot_refs", id, request) : id;
    }),
    http.delete("*/api/v1/shots/:id/refs/:idx", ({ params }) => {
      const id = shotOwner(params.id);
      return typeof id === "string" ? remove("shot_refs", id, Number(params.idx)) : id;
    }),
    http.post("*/api/v1/series/:id/style-board", ({ params, request }) =>
      add("style_board", String(params.id), request),
    ),
    http.delete("*/api/v1/series/:id/style-board/:idx", ({ params }) =>
      remove("style_board", String(params.id), Number(params.idx)),
    ),
  ];
}
