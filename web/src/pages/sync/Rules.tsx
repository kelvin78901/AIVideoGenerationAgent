/** 同步规则: when, what, how files are organised, and what metadata goes along. */
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useSaveSyncSettings } from "@/api/hooks/sync";
import { SYNC_EXTRAS, SYNC_KINDS, type SyncSettings, type SyncRules } from "@/api/schemas/sync";
import { Chip } from "@/components/Chip";
import { Checkbox } from "@/components/ui/checkbox";

const WHEN = ["adopt", "every", "manual"] as const;
const ORG = ["shot", "type"] as const;

const toggle = <T,>(list: readonly T[], v: T) =>
  list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

export function Rules({ settings }: { settings: SyncSettings }) {
  const { t } = useTranslation("sync");
  const { t: tc } = useTranslation();
  const save = useSaveSyncSettings();
  const { rules, preview } = settings;
  const set = (patch: Partial<SyncRules>) =>
    save.mutate({ rules: patch }, { onError: (err) => toast.error(errorMessage(tc, err)) });

  return (
    <section
      aria-labelledby="rules-title"
      className="flex min-w-0 flex-[999_1_480px] flex-col gap-3.5 rounded-xl border bg-card p-4.5"
    >
      <h2 id="rules-title" className="text-base font-bold">
        {t("rules.title")}
      </h2>
      <ChipGroup
        label={t("rules.when.label")}
        options={WHEN.map((v) => ({ value: v, label: t(`rules.when.${v}`) }))}
        value={rules.when}
        onChange={(when) => set({ when })}
      />
      <Boxes
        legend={t("rules.kinds.label")}
        options={SYNC_KINDS.map((k) => ({ value: k, label: t(`rules.kinds.${k}`) }))}
        checked={rules.kinds}
        onToggle={(k) => set({ kinds: toggle(rules.kinds, k) })}
      />
      <div className="flex flex-col gap-2">
        <ChipGroup
          label={t("rules.org.label")}
          options={ORG.map((v) => ({ value: v, label: t(`rules.org.${v}`) }))}
          value={rules.org}
          onChange={(org) => set({ org })}
        />
        <div
          aria-label={t("rules.preview")}
          className="rounded-lg bg-muted/60 px-3 py-2.5 font-mono text-xs leading-loose break-all text-muted-foreground"
        >
          <div>{preview.dir}</div>
          <div>{preview.files.join("  +  ")}</div>
        </div>
      </div>
      <Boxes
        legend={t("rules.extras.label")}
        options={SYNC_EXTRAS.map((k) => ({ value: k, label: t(`rules.extras.${k}`) }))}
        checked={rules.extras}
        onToggle={(k) => set({ extras: toggle(rules.extras, k) })}
        note={t("rules.extras.note")}
      />
    </section>
  );
}

function ChipGroup<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[13px] font-medium">{label}</div>
      <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
        {options.map((o) => (
          <Chip
            key={o.value}
            role="radio"
            selected={o.value === value}
            className="min-h-10 px-3.5 text-sm"
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </Chip>
        ))}
      </div>
    </div>
  );
}

function Boxes<T extends string>({
  legend,
  options,
  checked,
  onToggle,
  note,
}: {
  legend: string;
  options: { value: T; label: string }[];
  checked: readonly T[];
  onToggle: (v: T) => void;
  note?: string;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-[13px] font-medium">{legend}</legend>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-3 gap-y-0.5">
        {options.map((o) => (
          <label key={o.value} className="flex min-h-10 items-center gap-2 text-sm">
            <Checkbox
              checked={checked.includes(o.value)}
              onCheckedChange={() => onToggle(o.value)}
            />
            {o.label}
          </label>
        ))}
      </div>
      {note ? <p className="text-xs leading-relaxed text-muted-foreground">{note}</p> : null}
    </fieldset>
  );
}
