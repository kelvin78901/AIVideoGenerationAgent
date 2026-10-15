import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useSaveGenerateRules } from "@/api/hooks/generate";
import type { GenerateRules, GenerateRulesPatch } from "@/api/schemas/generate";
import { Input } from "@/components/ui/form";
import { formatPercent } from "@/lib/format";

type Field = keyof GenerateRulesPatch;

/** A number field saved on blur / Enter; out-of-range input snaps back. */
function RuleInput({
  id,
  value,
  min,
  max,
  step = 1,
  width,
  onSave,
}: {
  id: string;
  value: number;
  min: number;
  max?: number;
  step?: number;
  width: string;
  onSave: (n: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  const commit = () => {
    const n = Number(draft);
    const ok = draft !== "" && Number.isFinite(n) && n >= min && (max === undefined || n <= max);
    if (!ok || n === value) {
      setDraft(String(value));
      return;
    }
    onSave(n);
  };
  return (
    <Input
      id={id}
      type="number"
      inputMode="decimal"
      min={min}
      max={max}
      step={step}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && commit()}
      className={width}
    />
  );
}

/** 自动规则: takes per shot, QA reruns before fallback, per-shot cap, and the QA thresholds. */
export function RulesPanel({ seriesId, rules }: { seriesId: string; rules: GenerateRules }) {
  const { t } = useTranslation("generate");
  const { t: tc } = useTranslation();
  const save = useSaveGenerateRules(seriesId);
  const set = (field: Field) => (n: number) =>
    save.mutate({ [field]: n }, { onError: (err) => toast.error(errorMessage(tc, err)) });
  const row = "flex flex-wrap items-center gap-2 text-sm";
  const th = rules.thresholds;

  return (
    <section
      aria-labelledby="rules-title"
      className="flex min-w-0 flex-1 basis-80 flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <h2 id="rules-title" className="text-base font-bold">
        {t("rules.title")}
      </h2>
      <div className={row}>
        <label htmlFor="takes-n">{t("rules.takesBefore")}</label>
        <RuleInput
          id="takes-n"
          value={rules.takes_per_shot}
          min={1}
          max={6}
          width="w-16"
          onSave={set("takes_per_shot")}
        />
        <span>{t("rules.takesAfter")}</span>
      </div>
      <div className={row}>
        <label htmlFor="retry-n">{t("rules.retryBefore")}</label>
        <RuleInput
          id="retry-n"
          value={rules.qa_retry_max}
          min={0}
          max={5}
          width="w-16"
          onSave={set("qa_retry_max")}
        />
        <span>{t("rules.retryAfter")}</span>
      </div>
      <div className={row}>
        <label htmlFor="shot-cap">{t("rules.capBefore")}</label>
        <RuleInput
          id="shot-cap"
          value={rules.shot_cap_usd}
          min={0}
          step={0.5}
          width="w-20"
          onSave={set("shot_cap_usd")}
        />
        <span>{t("rules.capAfter")}</span>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("rules.thresholds", {
          face: th.face_sim,
          sync: th.syncnet_conf,
          cer: formatPercent(th.cer_max, 0),
        })}
      </p>
    </section>
  );
}
