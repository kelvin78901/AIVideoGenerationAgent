/** Helpers for demo handlers: every response is marked with the demo header (stores/demo.ts). */
import { HttpResponse, type JsonBodyType } from "msw";

import { API_BASE } from "@/api/client";
import { DEMO_HEADER } from "@/stores/demo";

/** Absolute path pattern for an `/api/v1` endpoint, e.g. `v1("/series/:id")`. */
export const v1 = (path: string) => `*${API_BASE}${path}`;

export function demoJson<T extends JsonBodyType>(body: T, init: ResponseInit = {}) {
  return HttpResponse.json(body, {
    ...init,
    headers: { ...init.headers, [DEMO_HEADER]: "1" },
  });
}

/** The backend's error shape: `{detail: {code, params}}`. */
export function demoError(status: number, code: string, params: Record<string, unknown> = {}) {
  return demoJson({ detail: { code, params } } as JsonBodyType, { status });
}
