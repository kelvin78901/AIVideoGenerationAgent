import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { BibleEntity } from "@/api/schemas/novel";

const COLUMNS = ["character", "location", "prop", "event"] as const;

/** 提取到的设定: the extract component's output in four columns. */
export function BiblePanel({
  entities,
  assetsPath,
}: {
  entities: BibleEntity[];
  assetsPath: string;
}) {
  const { t } = useTranslation("novel");
  return (
    <section
      aria-labelledby="novel-bible"
      className="flex flex-col gap-3 rounded-lg border bg-card p-4"
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="novel-bible" className="text-base font-bold">
          {t("bible.title")}
        </h2>
        <span className="text-xs text-muted-foreground">{t("bible.lead")}</span>
        <Link
          to={assetsPath}
          className="ml-auto text-sm text-primary underline-offset-4 hover:underline"
        >
          {t("bible.link")}
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {COLUMNS.map((kind) => {
          const items = entities.filter((e) => e.kind === kind);
          return (
            <div key={kind} className="flex flex-col gap-1.5">
              <h3 className="text-xs text-muted-foreground">{t(`bible.kind.${kind}`)}</h3>
              <ul aria-label={t(`bible.kind.${kind}`)} className="flex flex-col gap-1 text-sm">
                {items.map((e) => (
                  <li key={e.id}>
                    {e.name}
                    {e.data.summary ? ` · ${e.data.summary}` : ""}
                  </li>
                ))}
                {items.length === 0 ? (
                  <li className="text-muted-foreground">{t("bible.empty")}</li>
                ) : null}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
