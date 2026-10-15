/**
 * Demo handlers for `/api/v1` endpoints the backend does not implement yet. Requests without a
 * handler pass through to the real backend (jobs, providers, health, events, dev).
 *
 * When a milestone implements an endpoint, delete its handler here; when this list is empty,
 * delete `src/mocks/` (DECISIONS 2026-10-14 · M0.5).
 *
 * | Endpoint                         | Implemented in |
 * | -------------------------------- | -------------- |
 * | GET /series/{id}                 | M1             |
 * | GET /series/{id}/episodes        | M2             |
 * | GET /series/{id}/spec            | M1             |
 * | GET /episodes/{id}/progress      | M2             |
 * | GET /metrics/summary             | M8             |
 * | GET /metrics/kpis, spend-series, calls-series | M8 |
 * | GET /metrics/shots, components, speed, apis    | M8 |
 * | GET /metrics/local-models, qa, episodes, export.csv | M8 |
 * | GET /setup/profile               | M1             |
 * | GET /products, GET /products/{id} | M2             |
 * | POST /products/{id}/run          | M2             |
 * | POST /versions/{id}/set-current  | M2             |
 * | POST /versions/{id}/adopt        | M2             |
 * | POST /products/{id}/lock, unlock | M2             |
 * | PUT /products/{id}/prompt        | M2             |
 * | POST /products/{id}/compile      | M2             |
 * | GET /config/components           | M2             |
 * | GET /config/resolve              | M2             |
 * | PUT /config/override             | M2             |
 * | POST /impact/preview, apply      | M2             |
 * | POST /gates/{gate}/confirm, reopen | M2           |
 * | GET /series/{id}/novel           | M2             |
 * | GET /series/{id}/suggestions     | M2             |
 * | POST /series/{id}/suggestions/accept-all | M2     |
 * | POST /suggestions/{id}/accept, reject, reset, rewrite | M2 |
 * | GET /series/{id}/bible           | M2             |
 * | GET /episodes/{id}/script        | M2             |
 * | POST /lines/{id}/rewrite, /scenes/{id}/rewrite | M2 |
 * | GET /series/{id}/assets, PATCH /assets/{id} | M3   |
 * | POST /assets/{id}/lock           | M3             |
 * | POST /episodes/{id}/assets/analyze | M3           |
 * | GET /episodes/{id}/shots, PATCH /shots/{id} | M4  |
 * | POST /products/{id}/unadopt, PATCH /versions/{id} | M5 |
 * | GET, PUT /series/{id}/generate-rules | M5        |
 * | GET /episodes/{id}/generate-log  | M5             |
 * | POST /versions/{id}/upscale      | M6             |
 * | GET /episodes/{id}/timeline      | M7             |
 * | PATCH /clips/{id}, /subtitles/{id} | M7           |
 * | GET /episodes/{id}/export/checks, POST /episodes/{id}/export | M7 |
 * | PUT /series/{id}/spec, GET /spec/presets | M1     |
 * | GET /series/{id}/spec/compat     | M1             |
 * | POST /setup/scan, /setup/install | M1             |
 * | POST /setup/items/{id}/retry, skip | M1           |
 * | POST /demo/setup/machine (demo only, no backend) | — |
 * | GET, PUT /config/defaults, DELETE /config/override | M2 |
 * | PATCH /episodes/{id}             | M2             |
 * | GET, PUT /sync/targets, POST /sync/targets/{id}/detect | M9 |
 * | POST /sync/run, GET /sync/log, GET /sync/board | M9 |
 */
import { assetHandlers } from "@/mocks/handlers/assets";
import { configHandlers } from "@/mocks/handlers/config";
import { gateHandlers } from "@/mocks/handlers/gates";
import { generateHandlers } from "@/mocks/handlers/generate";
import { impactHandlers } from "@/mocks/handlers/impact";
import { metricsHandlers } from "@/mocks/handlers/metrics";
import { novelHandlers } from "@/mocks/handlers/novel";
import { postHandlers } from "@/mocks/handlers/post";
import { productHandlers } from "@/mocks/handlers/products";
import { scriptHandlers } from "@/mocks/handlers/script";
import { shotHandlers } from "@/mocks/handlers/shots";
import { specHandlers } from "@/mocks/handlers/spec";
import { syncHandlers } from "@/mocks/handlers/sync";
import { seriesHandlers } from "@/mocks/handlers/series";
import { setupHandlers } from "@/mocks/handlers/setup";

export const handlers = [
  ...seriesHandlers,
  ...metricsHandlers,
  ...setupHandlers,
  ...productHandlers,
  ...configHandlers,
  ...impactHandlers,
  ...gateHandlers,
  ...novelHandlers,
  ...scriptHandlers,
  ...assetHandlers,
  ...shotHandlers,
  ...generateHandlers,
  ...postHandlers,
  ...specHandlers,
  ...syncHandlers,
];
