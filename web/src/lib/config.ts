/** Reading a resolved component config (SPEC 7.1) the same way in pickers and pages. */
import type { ComponentConfig } from "@/api/schemas/config";

/** The model a plain run uses: local for local / hybrid (drafts), the API model otherwise. */
export function primaryModelKey(values: ComponentConfig): string | null {
  return values.mode === "api" ? values.api_model : (values.local_model ?? values.api_model);
}
