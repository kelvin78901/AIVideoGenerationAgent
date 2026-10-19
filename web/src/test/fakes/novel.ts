/**
 * Fake `/series/{id}/novel` for page tests: the demo novel chapter by chapter as the Mock backend
 * answers it, and the import preview of `雨停之前.txt` (`test/data/novel.json`, written by
 * tests/api/test_web_fixtures.py). Importing on another series stores that same novel there.
 * Suggestions and the bible of a series other than the demo are empty, as the backend's are
 * before anything ran.
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
};

export function resetFakeNovel() {
  fakeNovel.imported = new Set([DEMO_SERIES_ID]);
  fakeNovel.uploads = [];
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
      const novel = novelOf(id, idx);
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
      } satisfies NovelImport);
    }),

    // The backend's lists for a series nothing has run on yet (the demo's are MSW demo data).
    http.get("*/api/v1/series/:id/suggestions", ({ params }) =>
      String(params.id) !== DEMO_SERIES_ID && known(String(params.id))
        ? HttpResponse.json([])
        : undefined,
    ),
    http.get("*/api/v1/series/:id/bible", ({ params }) =>
      String(params.id) !== DEMO_SERIES_ID && known(String(params.id))
        ? HttpResponse.json([])
        : undefined,
    ),
  ];
}
