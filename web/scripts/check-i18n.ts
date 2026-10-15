/**
 * Fails when the zh-CN and en dictionaries differ: missing files, missing or extra keys,
 * or empty strings. Run by `pnpm test` and CI (CLAUDE.md hard rule 4).
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

export type Dict = { [key: string]: string | Dict };

const LOCALES = ["zh-CN", "en"] as const;

export function flatten(dict: Dict, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(dict)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out.set(path, value);
    else for (const [k, v] of flatten(value, path)) out.set(k, v);
  }
  return out;
}

export function compare(dicts: Record<string, Record<string, Dict>>): string[] {
  const problems: string[] = [];
  const [base, ...others] = LOCALES;
  const namespaces = new Set(LOCALES.flatMap((l) => Object.keys(dicts[l] ?? {})));
  for (const ns of [...namespaces].sort()) {
    const flat = Object.fromEntries(
      LOCALES.map((l) => [l, dicts[l]?.[ns] ? flatten(dicts[l][ns]) : undefined]),
    );
    for (const locale of LOCALES) {
      if (!flat[locale]) problems.push(`${locale}/${ns}.json is missing`);
    }
    const baseKeys = flat[base];
    if (!baseKeys) continue;
    for (const locale of others) {
      const keys = flat[locale];
      if (!keys) continue;
      for (const k of baseKeys.keys())
        if (!keys.has(k)) problems.push(`${locale}/${ns}: missing "${k}"`);
      for (const k of keys.keys())
        if (!baseKeys.has(k)) problems.push(`${base}/${ns}: missing "${k}"`);
    }
    for (const locale of LOCALES) {
      for (const [k, v] of flat[locale] ?? []) {
        if (!v.trim()) problems.push(`${locale}/${ns}: "${k}" is empty`);
      }
    }
  }
  return problems;
}

export function loadDicts(root: string): Record<string, Record<string, Dict>> {
  const dicts: Record<string, Record<string, Dict>> = {};
  for (const locale of LOCALES) {
    dicts[locale] = {};
    for (const file of readdirSync(join(root, locale)).filter((f) => f.endsWith(".json"))) {
      dicts[locale][file.replace(/\.json$/, "")] = JSON.parse(
        readFileSync(join(root, locale, file), "utf8"),
      ) as Dict;
    }
  }
  return dicts;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const root = fileURLToPath(new URL("../src/locales", import.meta.url));
  const problems = compare(loadDicts(root));
  if (problems.length) {
    console.error(`i18n check failed (${problems.length}):\n  ${problems.join("\n  ")}`);
    process.exit(1);
  }
  console.log("i18n check passed: zh-CN and en have the same keys");
}
