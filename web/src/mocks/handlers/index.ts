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
 */
import { configHandlers } from "@/mocks/handlers/config";
import { gateHandlers } from "@/mocks/handlers/gates";
import { impactHandlers } from "@/mocks/handlers/impact";
import { metricsHandlers } from "@/mocks/handlers/metrics";
import { productHandlers } from "@/mocks/handlers/products";
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
];
