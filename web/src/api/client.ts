import type { TFunction } from "i18next";
import { z } from "zod";

import { ApiErrorBodySchema, type ApiErrorBody } from "@/api/schemas/common";
import { DEMO_HEADER, useDemoStore } from "@/stores/demo";

export const API_BASE = "/api/v1";

/** A version file (picture, audio) by its content hash: `GET /files/{sha256}` (M3). */
export const fileUrl = (sha256: string) => `${API_BASE}/files/${sha256}`;

/** The backend rejects writes without this header (see `api/security.py`). */
export const CLIENT_HEADERS = { "X-Drama-Studio": "1" } as const;

/** A backend error: `code` + `params` are translated by the front end (SPEC 16.3). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly params: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.code);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.params = body.params;
  }
}

/**
 * Calls `/api/v1{path}` and validates the JSON response against `schema` (the API contract in
 * `api/schemas/`). A response that breaks the contract becomes `ApiError("bad_response")`, so a
 * backend or demo-data mismatch shows up at once instead of as a silently empty page.
 */
export async function api<S extends z.ZodType>(
  path: string,
  schema: S,
  init: RequestInit = {},
): Promise<z.infer<S>> {
  let resp: Response;
  // A FormData body sets its own multipart Content-Type (with the boundary).
  const json: Record<string, string> =
    init.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...json, ...CLIENT_HEADERS, ...init.headers },
    });
  } catch (err) {
    throw new ApiError(0, { code: "network", params: { message: String(err) } });
  }
  if (resp.headers.get(DEMO_HEADER) === "1") useDemoStore.getState().markDemoResponse();
  const text = await resp.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    throw new ApiError(resp.status, { code: "bad_response", params: { path, issues: "not JSON" } });
  }
  if (!resp.ok) {
    const detail = ApiErrorBodySchema.safeParse((data as { detail?: unknown } | null)?.detail);
    throw new ApiError(
      resp.status,
      detail.success ? detail.data : { code: `http_${resp.status}`, params: {} },
    );
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    const issues = z.prettifyError(parsed.error);
    console.error(`[api] ${path} does not match its schema:\n${issues}`);
    throw new ApiError(resp.status, { code: "bad_response", params: { path, issues } });
  }
  return parsed.data;
}

const send =
  (method: string) =>
  <S extends z.ZodType>(path: string, schema: S, body?: unknown) =>
    api(path, schema, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
    });

export const post = send("POST");
/** A multipart POST (file uploads). */
export const postForm = <S extends z.ZodType>(path: string, schema: S, form: FormData) =>
  api(path, schema, { method: "POST", body: form });
export const put = send("PUT");
export const patch = send("PATCH");
export const del = send("DELETE");

export function errorMessage(t: TFunction, err: unknown): string {
  if (err instanceof ApiError) {
    const key = `error.${err.code}`;
    // Unknown codes fall back to a generic message that still shows the code.
    return (
      t(key as "error.unknown", { ...err.params, code: err.code, defaultValue: "" }) ||
      t("error.unknown", { code: err.code })
    );
  }
  return t("error.unknown", { code: String(err) });
}

/** Fetches a file (CSV export …) as a Blob; errors are `ApiError`s like `api()`. */
export async function apiBlob(path: string): Promise<Blob> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, { headers: CLIENT_HEADERS });
  } catch (err) {
    throw new ApiError(0, { code: "network", params: { message: String(err) } });
  }
  if (resp.headers.get(DEMO_HEADER) === "1") useDemoStore.getState().markDemoResponse();
  if (!resp.ok) {
    const body: unknown = await resp.json().catch(() => null);
    const detail = ApiErrorBodySchema.safeParse((body as { detail?: unknown } | null)?.detail);
    throw new ApiError(
      resp.status,
      detail.success ? detail.data : { code: `http_${resp.status}`, params: {} },
    );
  }
  return resp.blob();
}
