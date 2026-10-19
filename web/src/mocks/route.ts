/**
 * The route a demo run uses. Run settings live in the real backend since M2, so the demo
 * handlers that remain read `GET /config/resolve` like the pages do (in tests that request is
 * answered by the fake backend, `test/fakes/config.ts`).
 */
import { ResolvedConfigSchema, type ComponentConfig } from "@/api/schemas/config";

export async function demoRoute(
  componentId: string,
  item: string | null = null,
): Promise<ComponentConfig | null> {
  const q = new URLSearchParams({ component: componentId });
  if (item) q.set("item", item);
  try {
    const resp = await fetch(`/api/v1/config/resolve?${q.toString()}`);
    if (!resp.ok) return null;
    const parsed = ResolvedConfigSchema.safeParse(await resp.json());
    return parsed.success ? parsed.data.values : null;
  } catch {
    return null;
  }
}

/** The model a plain run uses: local for local / hybrid drafts, the API model otherwise. */
export function primaryModel(cfg: ComponentConfig | null): string | null {
  if (!cfg || cfg.mode === "off") return null;
  return cfg.mode === "api" ? cfg.api_model : (cfg.local_model ?? cfg.api_model);
}
