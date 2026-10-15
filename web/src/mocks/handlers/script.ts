import { http } from "msw";

import type { ImpactChange } from "@/api/schemas/impact";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { primaryModel } from "@/mocks/fixtures/demo/config";
import { blockRewrites } from "@/mocks/fixtures/demo/script";
import { resolveConfig } from "@/mocks/handlers/config";
import { demoError, demoJson, v1 } from "@/mocks/http";

function findBlock(id: string) {
  for (const script of Object.values(getDb().scripts)) {
    const scene = script.scenes.find((s) => s.id === id);
    if (scene) return { scene };
    const line = script.lines.find((l) => l.id === id);
    if (line) return { line };
  }
  return undefined;
}

/** Writes a previewed change once the user picked 只标记 / 自动重跑 (`/impact/apply`). */
export function applyScriptChange(change: ImpactChange): void {
  const text = change.patch.text;
  if (typeof text !== "string") return;
  const block = findBlock(change.target_id);
  if (block?.scene) {
    block.scene.heading = text;
    block.scene.edited = true;
  } else if (block?.line) {
    block.line.text = text;
    block.line.edited = true;
  }
}

/** 「重写这一段」 / 「换模型重写」: returns a proposal after a short delay; saves nothing. */
function rewrite(kind: "lines" | "scenes") {
  return http.post(v1(`/${kind}/:id/rewrite`), async ({ params, request }) => {
    const id = String(params.id);
    if (!findBlock(id)) return demoError(404, "line_not_found", { id });
    const body = (await request.json().catch(() => ({}))) as { model?: unknown };
    const cfg = resolveConfig("script", null);
    const model =
      typeof body.model === "string" ? body.model : ((cfg && primaryModel(cfg.values)) ?? "");
    await new Promise((r) => setTimeout(r, demoTiming.rewriteMs));
    return demoJson({ text: blockRewrites[id] ?? "", model_key: model });
  });
}

export const scriptHandlers = [
  http.get(v1("/episodes/:id/script"), ({ params }) => {
    const id = String(params.id);
    if (!getDb().episodes.some((e) => e.id === id))
      return demoError(404, "episode_not_found", { id });
    return demoJson(getDb().scripts[id] ?? { episode_id: id, scenes: [], lines: [] });
  }),
  rewrite("lines"),
  rewrite("scenes"),
];
