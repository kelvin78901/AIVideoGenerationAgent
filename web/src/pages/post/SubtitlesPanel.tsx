import { useTranslation } from "react-i18next";

import type { Subtitle } from "@/api/schemas/timeline";
import { Input } from "@/components/ui/form";
import { formatClock } from "@/lib/format";

/** 字幕: one field per line; the preview and the timeline follow as you type, saved on blur. */
export function SubtitlesPanel({
  subtitles,
  onDraft,
  onSave,
}: {
  subtitles: Subtitle[];
  onDraft: (id: string, text: string) => void;
  onSave: (id: string, text: string) => void;
}) {
  const { t } = useTranslation("post");
  return (
    <section
      aria-labelledby="subs-title"
      className="flex min-w-0 flex-1 basis-80 flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <h2 id="subs-title" className="text-base font-bold">
        {t("subs.title")}
      </h2>
      <p className="text-xs leading-relaxed text-muted-foreground">{t("subs.lead")}</p>
      {subtitles.length ? (
        subtitles.map((s) => {
          const tc = t("subs.tc", {
            from: formatClock(s.start_s, { pad: true }),
            to: formatClock(s.end_s, { pad: true }),
          });
          return (
            <div key={s.id} className="flex flex-wrap items-center gap-2.5">
              <span className="w-28 shrink-0 font-mono text-xs text-muted-foreground" aria-hidden>
                {tc}
              </span>
              <Input
                aria-label={t("subs.label", { tc })}
                value={s.text}
                onChange={(e) => onDraft(s.id, e.target.value)}
                onBlur={(e) => onSave(s.id, e.target.value)}
                className="min-w-40 flex-1"
              />
              {s.edited ? (
                <span className="text-xs text-tone-warn-fg">{t("subs.edited")}</span>
              ) : null}
            </div>
          );
        })
      ) : (
        <p className="text-sm text-muted-foreground">{t("subs.empty")}</p>
      )}
    </section>
  );
}
