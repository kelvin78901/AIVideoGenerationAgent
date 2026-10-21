import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { AssetMatrix as Matrix } from "@/api/schemas/assets";
import { cn } from "@/lib/utils";

/**
 * 出场矩阵: one row per scene of the episode, one column per asset it uses (characters, scenes,
 * props, on-screen text, voices, as the list orders them). A filled cell is where the script
 * has the asset; it links to its first line there (a scene's own cell, to the scene).
 */
export function AssetMatrix({
  matrix,
  scriptPath,
  selectedId,
  onSelect,
}: {
  matrix: Matrix;
  scriptPath: string;
  selectedId: string;
  onSelect: (assetId: string) => void;
}) {
  const { t } = useTranslation("assets");
  const { t: te } = useTranslation("enums");
  const cells = new Map(matrix.cells.map((c) => [`${c.asset_id}|${c.scene_id}`, c.line_ids]));
  if (!matrix.scenes.length || !matrix.assets.length)
    return <p className="text-sm text-muted-foreground">{t("matrix.empty")}</p>;
  return (
    <section aria-label={t("matrix.label")} className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">{t("matrix.hint")}</p>
      <div className="overflow-x-auto rounded-lg border bg-card">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">{t("matrix.label")}</caption>
          <thead>
            <tr className="border-b">
              <th
                scope="col"
                className="sticky left-0 z-10 bg-card px-3 py-2 text-left text-xs font-medium text-muted-foreground"
              >
                {t("matrix.scene")}
              </th>
              {matrix.assets.map((a) => (
                <th key={a.id} scope="col" className="px-2 py-2 text-left align-bottom">
                  <button
                    type="button"
                    aria-pressed={a.id === selectedId}
                    onClick={() => onSelect(a.id)}
                    className={cn(
                      "flex flex-col rounded-md px-1.5 py-1 text-left outline-none hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring",
                      a.id === selectedId && "bg-tone-info-bg/60",
                    )}
                  >
                    <span className="text-xs font-normal text-muted-foreground">
                      {te(`assetKind.${a.kind}`)}
                    </span>
                    <span className="whitespace-nowrap font-medium">{a.name}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.scenes.map((s) => (
              <tr key={s.id} className="border-b last:border-b-0">
                <th
                  scope="row"
                  className="sticky left-0 z-10 max-w-56 bg-card px-3 py-2 text-left font-normal"
                >
                  <span className="font-medium">{t("detail.scene", { n: s.number })}</span>
                  <span className="block truncate text-xs text-muted-foreground">{s.heading}</span>
                </th>
                {matrix.assets.map((a) => {
                  const lines = cells.get(`${a.id}|${s.id}`);
                  if (!lines) return <td key={a.id} className="px-2 py-2" />;
                  const who = { kind: te(`assetKind.${a.kind}`), asset: a.name, n: s.number };
                  const label = lines.length
                    ? t("matrix.cellLines", { ...who, count: lines.length })
                    : t("matrix.cellScene", who);
                  return (
                    <td key={a.id} className="px-2 py-2">
                      <Link
                        to={`${scriptPath}?line=${encodeURIComponent(lines[0] ?? s.id)}`}
                        aria-label={label}
                        title={label}
                        className="inline-flex min-w-8 items-center justify-center rounded-md bg-tone-info-bg px-2 py-1 text-xs font-medium text-tone-info-fg tabular-nums underline-offset-4 hover:underline"
                      >
                        {lines.length ? lines.length : t("matrix.whole")}
                      </Link>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
