import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useSaveGenerateRules } from "@/api/hooks/generate";
import type {
  GenerateRules,
  GenerateRulesPatch,
  QaSwitches,
  QaThresholds,
} from "@/api/schemas/generate";
import { Input } from "@/components/ui/form";
import { Switch } from "@/components/ui/switch";

type Field = "takes_per_shot" | "qa_retry_max" | "shot_cap_usd";

/** A number field saved on blur / Enter; out-of-range input snaps back. Keyed by its value by
 * the caller, so a value changed elsewhere (恢复默认) shows. */
function RuleInput({
  id,
  value,
  min,
  max,
  step = 1,
  width,
  label,
  onSave,
}: {
  id: string;
  value: number;
  min: number;
  max?: number;
  step?: number;
  width: string;
  /** For a field without a <label> of its own (the thresholds table). */
  label?: string;
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
      aria-label={label}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && commit()}
      className={width}
    />
  );
}

/** One QA check in the thresholds table (草图 G3): its limit (none for OCR and the picture
 * check, which pass or fail), shown on screen ×`scale` (the error rate in %). */
interface CheckRow {
  metric: keyof QaSwitches;
  limit?: { key: keyof QaThresholds; sign: "≥" | "≤"; min: number; max: number; step: number };
  scale?: number;
}

const CHECKS: CheckRow[] = [
  { metric: "face", limit: { key: "face_sim", sign: "≥", min: 0, max: 1, step: 0.01 } },
  { metric: "lipsync", limit: { key: "syncnet_conf", sign: "≥", min: 0, max: 20, step: 0.1 } },
  { metric: "asr", limit: { key: "cer_max", sign: "≤", min: 0, max: 100, step: 1 }, scale: 100 },
  { metric: "speaker", limit: { key: "speaker_sim", sign: "≥", min: 0, max: 1, step: 0.01 } },
  { metric: "ocr" },
  { metric: "vlm" },
];

/** 自动规则: takes per shot, QA reruns before fallback, per-shot cap, and the series' QA
 * thresholds: each one editable and switchable (草图 G3); a change judges the takes again. */
export function RulesPanel({ seriesId, rules }: { seriesId: string; rules: GenerateRules }) {
  const { t } = useTranslation("generate");
  const { t: tc } = useTranslation();
  const save = useSaveGenerateRules(seriesId);
  const send = (patch: GenerateRulesPatch) =>
    save.mutate(patch, { onError: (err) => toast.error(errorMessage(tc, err)) });
  const set = (field: Field) => (n: number) => send({ [field]: n });
  const row = "flex flex-wrap items-center gap-2 text-sm";
  const th = rules.thresholds;

  return (
    <section
      aria-labelledby="rules-title"
      className="flex min-w-0 flex-1 basis-[30rem] flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <h2 id="rules-title" className="text-base font-bold">
        {t("rules.title")}
      </h2>
      <div className={row}>
        <label htmlFor="takes-n">{t("rules.takesBefore")}</label>
        <RuleInput
          id="takes-n"
          key={`takes-${rules.takes_per_shot}`}
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
          key={`retry-${rules.qa_retry_max}`}
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
          key={`cap-${rules.shot_cap_usd}`}
          value={rules.shot_cap_usd}
          min={0}
          step={0.5}
          width="w-20"
          onSave={set("shot_cap_usd")}
        />
        <span>{t("rules.capAfter")}</span>
      </div>
      <div className={row}>
        <span>{t("rules.lipsOnly")}</span>
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{t("rules.lipsAction")}</span>
        <span className="text-muted-foreground">{t("rules.lipsNote")}</span>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <h3 id="qa-thresholds" className="font-bold">
            {t("rules.qaTitle")}
          </h3>
          <span className="text-xs text-muted-foreground">{t("rules.qaLead")}</span>
        </div>
        <div className="overflow-x-auto">
          <table aria-labelledby="qa-thresholds" className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-1.5 pr-2 font-medium">{t("rules.colCheck")}</th>
                <th className="py-1.5 pr-2 font-medium">{t("rules.colLimit")}</th>
                <th className="py-1.5 pr-2 font-medium">{t("rules.colOn")}</th>
                <th className="py-1.5 font-medium">{t("rules.colNote")}</th>
              </tr>
            </thead>
            <tbody>
              {CHECKS.map((c) => {
                const name = t(`qa.${c.metric}`);
                const on = rules.qa_on[c.metric];
                const scale = c.scale ?? 1;
                const limit = c.limit;
                return (
                  <tr key={c.metric} className="border-b last:border-b-0">
                    <td className="py-1.5 pr-2 whitespace-nowrap">{name}</td>
                    <td className="py-1.5 pr-2">
                      {limit ? (
                        <span className="flex items-center gap-1.5 whitespace-nowrap">
                          <span aria-hidden>{limit.sign}</span>
                          <RuleInput
                            id={`qa-${c.metric}`}
                            key={`${c.metric}-${th[limit.key]}`}
                            label={t("rules.limitOf", { name })}
                            value={Math.round(th[limit.key] * scale * 100) / 100}
                            min={limit.min}
                            max={limit.max}
                            step={limit.step}
                            width="h-8 w-18"
                            onSave={(n) => send({ thresholds: { [limit.key]: n / scale } })}
                          />
                          {scale === 100 ? <span>%</span> : null}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">
                          {t(c.metric === "ocr" ? "rules.exact" : "rules.noIssue")}
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 pr-2">
                      <Switch
                        checked={on}
                        disabled={save.isPending}
                        aria-label={t("rules.switchOf", { name })}
                        onCheckedChange={(next) => send({ qa_on: { [c.metric]: next } })}
                      />
                    </td>
                    <td className="py-1.5 text-xs text-muted-foreground">
                      {t(`rules.note.${c.metric}`)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => send({ reset_qa: true })}
          className="self-end text-xs text-primary hover:underline disabled:text-muted-foreground"
        >
          {t("rules.reset")}
        </button>
      </div>
    </section>
  );
}
