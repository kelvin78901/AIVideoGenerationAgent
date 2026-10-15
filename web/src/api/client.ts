import type { TFunction } from "i18next";

import type { ApiErrorBody } from "@/api/types";

export const API_BASE = "/api/v1";

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

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" && value !== null && typeof (value as ApiErrorBody).code === "string"
  );
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...CLIENT_HEADERS, ...init.headers },
    });
  } catch (err) {
    throw new ApiError(0, { code: "network", params: { message: String(err) } });
  }
  const text = await resp.text();
  const data: unknown = text ? JSON.parse(text) : null;
  if (!resp.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(
      resp.status,
      isErrorBody(detail) ? detail : { code: `http_${resp.status}`, params: {} },
    );
  }
  return data as T;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

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
