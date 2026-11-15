import { Plus, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Asset } from "@/api/schemas/assets";
import {
  ContractKindSchema,
  DeliverySchema,
  type Shot,
  type ShotPatch,
  type StateItem,
} from "@/api/schemas/shots";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import type { ShotLine } from "@/pages/storyboard/ShotSettings";

const same = (a: StateItem[], b: StateItem[]) => JSON.stringify(a) === JSON.stringify(b);
const filled = (rows: StateItem[]) =>
  rows
    .map((r) => ({ subject: r.subject.trim(), state: r.state.trim() }))
    .filter((r) => r.subject && r.state);

/** 开始时 / 结束时: who or what, and how it is; saved on leaving a field. */
function StateTable({
  label,
  rows: given,
  disabled,
  note,
  onSave,
}: {
  label: string;
  rows: StateItem[];
  disabled: boolean;
  note?: string;
  onSave: (rows: StateItem[]) => void;
}) {
  const { t } = useTranslation("storyboard");
  const [rows, setRows] = useState<StateItem[]>(given);
  const save = (next: StateItem[]) => {
    const clean = filled(next);
    if (!same(clean, filled(given))) onSave(clean);
  };
  const set = (i: number, key: keyof StateItem, value: string) =>
    setRows(rows.map((r, n) => (n === i ? { ...r, [key]: value } : r)));
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
      <div className="text-sm font-medium">{label}</div>
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
      <div role="table" aria-label={label} className="flex flex-col gap-1">
        {rows.map((r, i) => (
          <div role="row" key={i} className="flex items-center gap-1.5">
            <Input
              aria-label={t("contract.subject")}
              className="w-28 shrink-0"
              value={r.subject}
              disabled={disabled}
              onChange={(e) => set(i, "subject", e.target.value)}
              onBlur={() => save(rows)}
            />
            <Input
              aria-label={t("contract.state")}
              className="min-w-0 flex-1"
              value={r.state}
              disabled={disabled}
              onChange={(e) => set(i, "state", e.target.value)}
              onBlur={() => save(rows)}
            />
            <Button
              size="icon"
              variant="ghost"
              aria-label={t("contract.removeRow")}
              disabled={disabled}
              onClick={() => {
                const next = rows.filter((_, n) => n !== i);
                setRows(next);
                save(next);
              }}
            >
              <X aria-hidden />
            </Button>
          </div>
        ))}
      </div>
      <div>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled}
          onClick={() => setRows([...rows, { subject: "", state: "" }])}
        >
          <Plus aria-hidden />
          {t("contract.addRow")}
        </Button>
      </div>
    </div>
  );
}

/** 镜头契约 (M5.5, sketch S2): how the shot plays, how it starts and ends, the props as set, how
 * each line is said. The keyframe draws its start; the video keeps to it; a change marks both
 * 待更新. A confirmed shot's change goes through the impact preview (the page's `edit`). */
export function ContractSection({
  shot,
  lines,
  assets,
  disabled,
  onPatch,
}: {
  shot: Shot;
  lines: ShotLine[];
  assets: Asset[];
  disabled: boolean;
  onPatch: (patch: ShotPatch) => void;
}) {
  const { t } = useTranslation("storyboard");
  const c = shot.contract;
  const props = shot.asset_ids.flatMap(
    (id) => assets.find((a) => a.id === id && (a.kind === "prop" || a.kind === "text")) ?? [],
  );
  // The scene's states (`props_inherited`, `props_linked`) are shown, not this shot's own.
  const fromScene = new Set([...c.props_inherited, ...c.props_linked]);
  const own = c.props.filter((p) => !fromScene.has(p.asset_id));
  const sceneState = Object.fromEntries(c.props.map((p) => [p.asset_id, p.state]));
  const linked = c.props_linked.flatMap((id) => assets.find((a) => a.id === id) ?? []);
  const [states, setStates] = useState<Record<string, string>>(
    Object.fromEntries(own.map((p) => [p.asset_id, p.state])),
  );
  const saveProps = () => {
    const next = props
      .map((a) => ({ asset_id: a.id, state: (states[a.id] ?? "").trim() }))
      .filter((p) => p.state);
    if (JSON.stringify(next) !== JSON.stringify(own)) onPatch({ contract: { props: next } });
  };
  const spoken = Object.keys(c.delivery).flatMap((id) => lines.find((l) => l.id === id) ?? []);
  return (
    <section aria-label={t("contract.label")} className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-bold">{t("contract.title")}</h3>
        <p className="text-xs text-muted-foreground">{t("contract.hint")}</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <SegmentedControl
          label={t("contract.kind")}
          value={c.kind}
          onChange={(kind) => onPatch({ contract: { kind } })}
          options={ContractKindSchema.options.map((k) => ({
            value: k,
            label: t(`contract.kinds.${k}`),
            disabled,
          }))}
        />
        <p className="text-xs text-muted-foreground">
          {t(`contract.kindHint.${c.kind}`, { n: c.beats })}
        </p>
      </div>
      <div className="flex flex-col gap-3 md:flex-row">
        <StateTable
          label={t("contract.start")}
          rows={c.start}
          disabled={disabled}
          note={
            c.start_inherited ? t("contract.inherited", { id: shot.tail_from ?? "" }) : undefined
          }
          onSave={(start) => onPatch({ contract: { start } })}
        />
        <StateTable
          label={t("contract.end")}
          rows={c.end}
          disabled={disabled}
          onSave={(end) => onPatch({ contract: { end } })}
        />
      </div>
      {props.length || linked.length ? (
        <div className="flex flex-col gap-1.5">
          <div className="text-sm font-medium">
            {t("contract.props")}{" "}
            <span className="font-normal text-muted-foreground">{t("contract.propsHint")}</span>
          </div>
          {props.map((a) => (
            <label key={a.id} className="flex items-center gap-2 text-sm">
              <span className="w-28 shrink-0 truncate">{a.name}</span>
              <Input
                aria-label={t("contract.propState", { name: a.name })}
                className="min-w-0 flex-1"
                value={states[a.id] ?? ""}
                placeholder={
                  c.props_inherited.includes(a.id)
                    ? t("contract.propInherited", { state: sceneState[a.id] })
                    : undefined
                }
                disabled={disabled}
                onChange={(e) => setStates({ ...states, [a.id]: e.target.value })}
                onBlur={saveProps}
              />
            </label>
          ))}
          {linked.map((a) => (
            <div key={a.id} className="flex items-center gap-2 text-sm">
              <span className="w-28 shrink-0 truncate">{a.name}</span>
              <span className="min-w-0 flex-1 text-muted-foreground">
                {t("contract.propLinked", { state: sceneState[a.id] })}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {spoken.length ? (
        <div className="flex flex-col gap-1.5">
          <div className="text-sm font-medium">{t("contract.delivery")}</div>
          {spoken.map((l) => (
            <div key={l.id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="min-w-0 flex-1">
                {l.lead}
                {l.text}
              </span>
              <SegmentedControl
                size="sm"
                label={t("contract.deliveryOf", { text: l.text })}
                value={c.delivery[l.id] ?? "dialogue"}
                onChange={(how) => onPatch({ contract: { delivery: { [l.id]: how } } })}
                options={DeliverySchema.options.map((d) => ({
                  value: d,
                  label: t(`contract.how.${d}`),
                  disabled,
                }))}
              />
            </div>
          ))}
          <p className="text-xs text-muted-foreground">{t("contract.deliveryHint")}</p>
        </div>
      ) : null}
    </section>
  );
}
