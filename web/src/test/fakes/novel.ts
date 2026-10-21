/**
 * Fake `/series/{id}/novel` for page tests: the demo novel chapter by chapter as the Mock backend
 * answers it, and the import preview of `雨停之前.txt` (`test/data/novel.json`, written by
 * tests/api/test_web_fixtures.py). Importing on another series stores that same novel there.
 * Editing a chapter (`PUT …/chapters/{idx}`) changes the demo's text the way the backend does:
 * a line break starts a paragraph, empty ones go, paragraphs are numbered again across the book.
 */
import { http, HttpResponse } from "msw";

import { NovelImportSchema, NovelSchema, type Novel, type NovelImport } from "@/api/schemas/novel";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import data from "@/test/data/novel.json";

const chapters = data.chapters.map((c) => NovelSchema.parse(c));
const preview = NovelImportSchema.parse(data.preview);

export interface FakeUpload {
  series: string;
  filename: string;
  dryRun: boolean;
  rights: boolean;
}

/** State of the fake; `resetFakeNovel()` (called by `backend()`) restores it. */
export const fakeNovel = {
  /** Series with a novel; the demo series always has one. */
  imported: new Set<string>([DEMO_SERIES_ID]),
  uploads: [] as FakeUpload[],
  /** The demo novel as `GET …?chapter=` answers each chapter. */
  chapters: structuredClone(chapters),
  /** Every chapter edit sent, in order. */
  edits: [] as { idx: number; title: string | null; paragraphs: string[] }[],
};

export function resetFakeNovel() {
  fakeNovel.imported = new Set([DEMO_SERIES_ID]);
  fakeNovel.uploads = [];
  fakeNovel.chapters = structuredClone(chapters);
  fakeNovel.edits = [];
}

/** One chapter replaced; paragraph numbers, offsets and counts recomputed for the book. */
function applyEdit(idx: number, title: string | null, paragraphs: string[]): Novel {
  const all = fakeNovel.chapters;
  const texts = paragraphs.flatMap((t) => t.split("\n").map((s) => s.trim())).filter(Boolean);
  const edited = all[idx];
  if (!edited) throw new Error(`no chapter ${idx}`);
  edited.paragraphs = texts.map((text) => ({ idx: 0, text, start: 0, end: 0 }));
  let n = 0;
  let pos = 0;
  const metas = edited.chapters.map((chapter, i) => {
    const novel = all[i] ?? edited;
    const meta = { ...chapter, para_start: n, para_count: novel.paragraphs.length };
    if (i === idx) meta.title = title?.trim() || null;
    meta.start = pos;
    for (const p of novel.paragraphs) {
      Object.assign(p, { idx: n++, start: pos, end: pos + p.text.length });
      pos += p.text.length + 1;
    }
    meta.end = pos;
    meta.chars = novel.paragraphs.reduce((sum, p) => sum + p.text.length, 0);
    return meta;
  });
  const source = edited.source && {
    ...edited.source,
    id: `${edited.source.id}-e${fakeNovel.edits.length}`,
    encoding: "edited" as const,
    chars: metas.reduce((sum, c) => sum + c.chars, 0),
  };
  for (const novel of all) Object.assign(novel, { chapters: metas, source });
  return edited;
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

function novelOf(series: string, chapter: number): Novel | undefined {
  const c = chapters[chapter];
  return c && { ...structuredClone(c), series_id: series };
}

/** `known`: the series the fake backend has. */
export function novelHandlers(known: (id: string) => boolean) {
  return [
    http.get("*/api/v1/series/:id/novel", ({ params, request }) => {
      const id = String(params.id);
      if (!known(id)) return error(404, "series_not_found", { id });
      if (!fakeNovel.imported.has(id))
        return HttpResponse.json({
          series_id: id,
          source: null,
          chapters: [],
          chapter: null,
          paragraphs: [],
        } satisfies Novel);
      const idx = Number(new URL(request.url).searchParams.get("chapter") ?? 0);
      const novel = id === DEMO_SERIES_ID ? fakeNovel.chapters[idx] : novelOf(id, idx);
      return novel ? HttpResponse.json(novel) : error(404, "chapter_not_found", { idx });
    }),

    http.post("*/api/v1/series/:id/novel", async ({ params, request }) => {
      const id = String(params.id);
      if (!known(id)) return error(404, "series_not_found", { id });
      const form = await request.formData();
      const file = form.get("file");
      const upload: FakeUpload = {
        series: id,
        filename: file instanceof File ? file.name : "",
        dryRun: form.get("dry_run") === "true",
        rights: form.get("rights_confirmed") === "true",
      };
      fakeNovel.uploads.push(upload);
      if (!/\.(txt|docx)$/i.test(upload.filename))
        return error(415, "unsupported_file", { ext: upload.filename.replace(/^.*(?=\.)/, "") });
      const found: NovelImport = { ...structuredClone(preview), filename: upload.filename };
      if (upload.dryRun) return HttpResponse.json(found);
      if (!upload.rights) return error(422, "rights_not_confirmed");
      fakeNovel.imported.add(id);
      return HttpResponse.json({
        ...found,
        dry_run: false,
        source_id: `${id}-src`,
        chapters: found.chapters.map((c) => ({ ...c, id: `${id}-src-ch${c.idx + 1}` })),
        upload_id: null,
      } satisfies NovelImport);
    }),

    http.put("*/api/v1/series/:id/novel/chapters/:idx", async ({ params, request }) => {
      const id = String(params.id);
      if (!known(id)) return error(404, "series_not_found", { id });
      if (id !== DEMO_SERIES_ID) return error(404, "novel_not_found", { id });
      const idx = Number(params.idx);
      if (!fakeNovel.chapters[idx]) return error(404, "chapter_not_found", { idx });
      const body = (await request.json()) as { title: string | null; paragraphs: string[] };
      fakeNovel.edits.push({ idx, ...body });
      if (!body.paragraphs.some((p) => p.trim())) return error(422, "chapter_empty", { idx });
      return HttpResponse.json(applyEdit(idx, body.title, body.paragraphs));
    }),
  ];
}
