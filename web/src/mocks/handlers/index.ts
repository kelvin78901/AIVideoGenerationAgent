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
 */
import { metricsHandlers } from "@/mocks/handlers/metrics";
import { seriesHandlers } from "@/mocks/handlers/series";
import { setupHandlers } from "@/mocks/handlers/setup";

export const handlers = [...seriesHandlers, ...metricsHandlers, ...setupHandlers];
