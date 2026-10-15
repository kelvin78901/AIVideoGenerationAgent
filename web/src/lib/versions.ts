/** Reading a product's versions (SPEC 4.2) the same way in RunBar, Inspector and pages. */
import type { ModelOption } from "@/api/schemas/models";
import type { Product, ProductVersion } from "@/api/schemas/products";

/** The version the UI shows: `current_version_id`, else the newest. */
export function currentVersion(product: Product): ProductVersion | undefined {
  return (
    product.versions.find((v) => v.id === product.current_version_id) ?? product.versions.at(-1)
  );
}

export type VersionStatus = "locked" | "adopted" | "draft";

export function versionStatus(product: Product, version: ProductVersion): VersionStatus {
  if (version.id !== product.adopted_version_id) return "draft";
  return product.locked_hash ? "locked" : "adopted";
}

/** `enums:origin.<key>`; adds `first` (v1) and `prompt_rerun` (rerun with an edited prompt). */
export type OriginLabel = ProductVersion["origin"] | "first" | "prompt_rerun";

export function originLabel(product: Product, version: ProductVersion): OriginLabel {
  if (version.origin === "run" && version.n === 1) return "first";
  if (version.origin === "rerun") {
    const parent = product.versions.find((v) => v.id === version.parent_version_id);
    if (
      parent &&
      (parent.intent !== version.intent ||
        (version.compiled_overridden && parent.compiled !== version.compiled))
    )
      return "prompt_rerun";
  }
  return version.origin;
}

/** Display name of a model key; unknown keys show as is. */
export function modelName(models: readonly ModelOption[], key: string | null | undefined): string {
  if (!key) return "";
  return models.find((m) => m.key === key)?.display ?? key;
}
