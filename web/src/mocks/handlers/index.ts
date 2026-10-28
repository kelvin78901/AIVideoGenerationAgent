/**
 * Demo handlers for `/api/v1` endpoints the backend does not implement yet. Requests without a
 * handler pass through to the real backend (jobs, providers, health, events, dev).
 *
 * When a milestone implements an endpoint, delete its handler here; when this list is empty,
 * delete `src/mocks/` (DECISIONS 2026-10-14 · M0.5).
 *
 * Implemented and removed: GET /series/{id}, GET / PUT /series/{id}/spec,
 * GET /series/{id}/spec/compat, GET /spec/presets, GET /setup/profile, POST /setup/scan,
 * POST /setup/install, POST /setup/items/{id}/retry|skip, POST /demo/setup/machine (now the
 * backend's POST /dev/setup/machine) (M1). GET /config/components, GET /config/resolve,
 * PUT / DELETE /config/override, GET / PUT /config/defaults, GET /series/{id}/novel,
 * GET /series/{id}/bible, PATCH /bible/{id}, POST /bible/merge, GET /series/{id}/suggestions,
 * POST /series/{id}/suggestions/accept-all, POST /suggestions/{id}/accept|reject|reset|rewrite,
 * PATCH /episodes/{id}, PATCH /beats/{id}, GET /episodes/{id}/script, PATCH /lines/{id},
 * PATCH /scenes/{id}, POST /lines/{id}/rewrite, POST /scenes/{id}/rewrite (M2).
 * PATCH /assets/{id}, POST /assets/{id}/lock|upload, POST /episodes/{id}/assets/analyze,
 * GET /episodes/{id}/assets/matrix, the asset products and `asset_unlock` (M3).
 * PATCH /shots/{id}, POST /shots/{id}/split|merge, the 分镜规划 and keyframe products, the
 * storyboard gate, `spec_aspect` and `shot_edit` (M4).
 * GET /episodes/{id}/progress and GET /episodes/{id}/shots are the backend's too; the demo lays
 * episode 1's 后期 over the badges until M7. The video takes and 生成确认, GET / PUT
 * /series/{id}/generate-rules, GET /episodes/{id}/generate-log, POST /products/{id}/unadopt,
 * PATCH /versions/{id} and the impact previews' videos (M5). GET /metrics/summary is the
 * backend's with the demo's dashboard numbers on top until M8.
 * Never demo data: GET / POST /series, PATCH /series/{id}, POST /series/{id}/novel.
 *
 * Handlers that take a series answer only for the demo series; any other series passes through
 * to the backend (plan M2「和 MSW 共存」).
 *
 * | Endpoint                         | Implemented in |
 * | -------------------------------- | -------------- |
 * | GET /metrics/summary             | M8             |
 * | GET /metrics/kpis, spend-series, calls-series | M8 |
 * | GET /metrics/shots, components, speed, apis    | M8 |
 * | GET /metrics/local-models, qa, episodes, export.csv | M8 |
 * | GET /products, GET /products/{id} | M2             |
 * | POST /products/{id}/run          | M2             |
 * | POST /versions/{id}/set-current  | M2             |
 * | POST /versions/{id}/adopt        | M2             |
 * | POST /products/{id}/lock, unlock | M2             |
 * | PUT /products/{id}/prompt        | M2             |
 * | POST /products/{id}/compile      | M2             |
 * | POST /gates/{gate}/confirm, reopen | M2           |
 * | POST /versions/{id}/upscale      | M6             |
 * | GET /episodes/{id}/timeline      | M7             |
 * | PATCH /clips/{id}, /subtitles/{id} | M7           |
 * | GET /episodes/{id}/export/checks, POST /episodes/{id}/export | M7 |
 * | GET, PUT /sync/targets, POST /sync/targets/{id}/detect | M9 |
 * | POST /sync/run, GET /sync/log, GET /sync/board | M9 |
 * | GET /workflows, GET / PATCH /workflows/{id}, POST /workflows/import | M5 |
 * | PUT /workflows/{id}/bindings, POST /workflows/{id}/check, /trial | M5 |
 * | POST /workflows/check-all, /workflows/{id}/deps, /deps/install | M5 |
 * | GET /comfy/workflows (ComfyUI's own workflow list) | M5 |
 */
import { gateHandlers } from "@/mocks/handlers/gates";
import { generateHandlers } from "@/mocks/handlers/generate";
import { metricsHandlers } from "@/mocks/handlers/metrics";
import { postHandlers } from "@/mocks/handlers/post";
import { productHandlers } from "@/mocks/handlers/products";
import { syncHandlers } from "@/mocks/handlers/sync";
import { workflowHandlers } from "@/mocks/handlers/workflows";
import { seriesHandlers } from "@/mocks/handlers/series";

export const handlers = [
  ...seriesHandlers,
  ...metricsHandlers,
  ...productHandlers,
  ...gateHandlers,
  ...generateHandlers,
  ...postHandlers,
  ...syncHandlers,
  ...workflowHandlers,
];
