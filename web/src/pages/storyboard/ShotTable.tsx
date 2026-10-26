import { Combine, Scissors } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Asset } from "@/api/schemas/assets";
import {
  CameraMoveSchema,
  FramingSchema,
  ShotTypeSchema,
  type Shot,
  type ShotPatch,
} from "@/api/schemas/shots";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { durationSource } from "@/pages/storyboard/duration";

const LETTERS = "ABC";
const SELECT =
  "h-7 rounded-md border bg-card px-1.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";
const COLUMNS = [
  "shot",
  "scene",
  "type",
  "framing",
  "move",
  "duration",
  "dialogue",
  "refs",
  "keyframe",
  "status",
  "actions",
] as const;

/** The length cell: typed in, saved on leaving it (never shorter than the audio). */
function Duration({ shot, onPatch }: { shot: Shot; onPatch: (change: ShotPatch) => void }) {
  const { t } = useTranslation("storyboard");
  const [value, setValue] = useState(String(shot.duration_s));
  return (
    <input
      type="number"
      min={shot.min_s || 0.5}
      max={60}
      step={0.5}
      aria-label={t("table.durationOf", { id: shot.label })}
      className={`${SELECT} w-16 tabular-nums`}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        const n = Number(value);
        if (Number.isFinite(n) && n > 0 && n <= 60 && n !== shot.duration_s)
          onPatch({ duration_s: n });
        else setValue(String(shot.duration_s));
      }}
    />
  );
}

/**
 * 表格视图: one row per shot, its settings edited in the cell (the same PATCH as the board;
 * a confirmed shot's goes through the impact preview), 拆分 / 和下一个合并 per row. A row's shot
 * is the one selected on the board too (`?shot=`).
 */
export function ShotTable({
  shots,
  assets,
  selectedId,
  busy,
  onSelect,
  onPatch,
  onSplit,
  onMerge,
}: {
  shots: Shot[];
  assets: Asset[];
  selectedId: string;
  busy: boolean;
  onSelect: (id: string) => void;
  onPatch: (shot: Shot, change: ShotPatch) => void;
  onSplit: (shot: Shot) => void;
  onMerge: (shot: Shot) => void;
}) {
  const { t } = useTranslation("storyboard");
  const { t: te } = useTranslation("enums");
  const name = (id: string) => assets.find((a) => a.id === id)?.name ?? id;
  return (
    <section aria-label={t("table.label")} className="overflow-x-auto rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            {COLUMNS.map((c) => (
              <TableHead key={c} className="whitespace-nowrap">
                {t(`table.col.${c}`)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {shots.map((s, i) => {
            const next = shots[i + 1];
            const canMerge = next?.scene_id === s.scene_id;
            const patch = (change: ShotPatch) => onPatch(s, change);
            const source = durationSource(s);
            return (
              <TableRow key={s.id} data-state={s.id === selectedId ? "selected" : undefined}>
                <TableCell>
                  <button
                    type="button"
                    aria-pressed={s.id === selectedId}
                    onClick={() => onSelect(s.id)}
                    className="rounded-sm font-mono text-xs font-medium whitespace-nowrap text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {s.label}
                  </button>
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {t("shot.scene", { n: s.scene_no, place: s.scene_place })}
                </TableCell>
                <TableCell>
                  <select
                    className={SELECT}
                    aria-label={t("table.typeOf", { id: s.label })}
                    value={s.shot_type}
                    disabled={busy}
                    onChange={(e) => patch({ shot_type: ShotTypeSchema.parse(e.target.value) })}
                  >
                    {ShotTypeSchema.options.map((v) => (
                      <option key={v} value={v}>
                        {te(`shotType.${v}`)}
                      </option>
                    ))}
                  </select>
                </TableCell>
                <TableCell>
                  <select
                    className={SELECT}
                    aria-label={t("table.framingOf", { id: s.label })}
                    value={s.framing}
                    disabled={busy}
                    onChange={(e) => patch({ framing: FramingSchema.parse(e.target.value) })}
                  >
                    {FramingSchema.options.map((v) => (
                      <option key={v} value={v}>
                        {te(`framing.${v}`)}
                      </option>
                    ))}
                  </select>
                </TableCell>
                <TableCell>
                  <select
                    className={SELECT}
                    aria-label={t("table.moveOf", { id: s.label })}
                    value={s.camera_move}
                    disabled={busy}
                    onChange={(e) => patch({ camera_move: CameraMoveSchema.parse(e.target.value) })}
                  >
                    {CameraMoveSchema.options.map((v) => (
                      <option key={v} value={v}>
                        {te(`cameraMove.${v}`)}
                      </option>
                    ))}
                  </select>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <Duration key={`${s.id}-${s.duration_s}`} shot={s} onPatch={patch} />
                    <span
                      className={
                        s.split_hint
                          ? "text-xs whitespace-nowrap text-tone-warn-fg"
                          : "text-xs whitespace-nowrap text-muted-foreground"
                      }
                      title={
                        s.split_hint && s.longest_s !== null
                          ? t("shot.splitHint", { max: s.longest_s })
                          : undefined
                      }
                    >
                      {t(`table.source.${source}`)}
                    </span>
                  </div>
                </TableCell>
                <TableCell className="min-w-48 text-xs whitespace-normal">
                  {s.dialogue ?? t("table.none")}
                </TableCell>
                <TableCell className="min-w-32 text-xs whitespace-normal">
                  {s.asset_ids.length ? s.asset_ids.map(name).join("、") : t("table.none")}
                </TableCell>
                <TableCell className="text-xs whitespace-nowrap">
                  {s.shot_type === "continuous"
                    ? t("table.kfTail", { id: s.tail_from ?? "" })
                    : s.keyframe_product_id
                      ? t("table.kfPick", { letter: LETTERS[s.keyframe_pick] ?? "A" })
                      : t("table.kfNone")}
                </TableCell>
                <TableCell>
                  <StatusBadge tone={s.confirmed && !s.confirm_stale ? "info" : "warn"} icon={null}>
                    {t(
                      s.confirm_stale
                        ? "status.stale"
                        : s.confirmed
                          ? "status.confirmed"
                          : "status.draft",
                    )}
                  </StatusBadge>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      aria-label={t("table.splitOf", { id: s.label })}
                      title={t("table.splitOf", { id: s.label })}
                      disabled={busy}
                      onClick={() => onSplit(s)}
                    >
                      <Scissors aria-hidden />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      aria-label={t("table.mergeOf", { id: s.label })}
                      title={canMerge ? t("table.mergeOf", { id: s.label }) : t("shot.mergeNone")}
                      disabled={busy || !canMerge}
                      onClick={() => onMerge(s)}
                    >
                      <Combine aria-hidden />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </section>
  );
}
