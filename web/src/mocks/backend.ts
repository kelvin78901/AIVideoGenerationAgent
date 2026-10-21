/**
 * The real backend's answer to a request the demo also answers, for the few lists that merge
 * both (plan「和 MSW 共存」): e.g. the demo series' products, part of which (the novel, 设定提取)
 * already live in the backend. Page tests point it at their fake backend (`test/backend.ts`).
 */
import { bypass } from "msw";

type BackendFetch = (request: Request) => Promise<Response>;

const realBackend: BackendFetch = (request) => fetch(bypass(request));
let fetchBackend: BackendFetch = realBackend;

export function setBackendFetch(fn: BackendFetch | null): void {
  fetchBackend = fn ?? realBackend;
}

/** The backend's response to this request (errors included); null when it is down. */
export async function backendResponse(request: Request): Promise<Response | null> {
  try {
    return await fetchBackend(request);
  } catch {
    return null;
  }
}

/** The backend's JSON for this request; `fallback` when it is down or answers an error. */
export async function backendJson<T>(request: Request, fallback: T): Promise<T> {
  try {
    const resp = await fetchBackend(request);
    return resp.ok ? ((await resp.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}
