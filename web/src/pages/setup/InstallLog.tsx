/** The install log: `setup.log` events, newest at the bottom. */
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import type { SetupLog } from "@/api/schemas/setup";
import { cn } from "@/lib/utils";

const levelClass: Record<SetupLog["level"], string> = {
  info: "text-media-foreground",
  ok: "text-media-ok",
  warn: "text-media-warn",
};

export function InstallLog({
  lines,
  itemName,
}: {
  lines: SetupLog[];
  /** Log params carry item ids; the page shows their names. */
  itemName: (id: string) => string;
}) {
  const { t } = useTranslation("setup");
  const list = useRef<HTMLOListElement>(null);
  // Keep the newest line in view without scrolling the page itself.
  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [lines.length]);

  const text = (l: SetupLog) => {
    const params: Record<string, string | number> = { ...l.params };
    if (typeof params.item === "string") params.item = itemName(params.item);
    if (typeof params.mirror === "string")
      params.mirror = t(`mirror.name.${params.mirror}` as "mirror.name.auto");
    return t(`log.${l.code}` as "log.finish", { ...params, defaultValue: l.code });
  };

  return (
    <section
      aria-labelledby="install-log-title"
      className="flex flex-col gap-1 rounded-xl bg-media px-4 py-3.5"
    >
      <h2 id="install-log-title" className="mb-1 text-xs font-normal text-media-muted">
        {t("log.title")}
      </h2>
      <ol ref={list} aria-live="polite" className="flex max-h-56 flex-col overflow-y-auto">
        {lines.map((l, i) => (
          <li
            key={i}
            className={cn(
              "font-mono text-xs leading-relaxed",
              l.code === "mirror" ? "text-media-muted" : levelClass[l.level],
            )}
          >
            {text(l)}
          </li>
        ))}
      </ol>
    </section>
  );
}
