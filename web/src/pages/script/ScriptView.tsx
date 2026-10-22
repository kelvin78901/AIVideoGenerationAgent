import { ArrowLeftRight, Clapperboard, Pencil, RotateCw } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { fileUrl } from "@/api/client";
import type { DubLine } from "@/api/schemas/dub";
import type { ModelOption } from "@/api/schemas/models";
import { AudioPlayer } from "@/components/AudioPlayer";
import { ModelSwitchMenu } from "@/components/ModelSwitchMenu";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/form";
import { Label } from "@/components/ui/form";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fromAddition, useBlockLead, type Block, type DubIndex } from "@/pages/script/blocks";

function useBlockText() {
  const { t } = useTranslation("script");
  const lead = useBlockLead();
  const paras = (b: Block) => b.paras.map((i) => i + 1).join(t("script.paraSep"));
  const ai = (b: Block) => b.kind !== "scene" && b.line.ai_added;
  const from = (b: Block) => (fromAddition(b) ? "addition" : "source");
  return {
    lead,
    prov: (b: Block, pending: boolean) =>
      pending || b.edited
        ? t("script.prov.edited")
        : ai(b)
          ? t("script.prov.ai")
          : t(`script.prov.${from(b)}`, { paras: paras(b) }),
    srcLabel: (b: Block) =>
      ai(b) ? t("script.srcLabel.ai") : t(`script.srcLabel.${from(b)}`, { paras: paras(b) }),
    flagged: (b: Block, pending: boolean) => pending || b.edited || ai(b),
  };
}

export interface ScriptActions {
  onSave: (block: Block, text: string) => void;
  /** `confirmBudget`: the user agreed to a rewrite over the budget. */
  onRewrite: (block: Block, model?: string, confirmBudget?: boolean) => void;
}

/** 镜头 ↔ 剧本行 and 剧本行 → 原文 (M2 step 9): where a selected block links to. */
export interface ScriptLinks {
  /** The shots that film this line (示例分镜 until M4). */
  shotsOf: (block: Block) => { id: string; label: string }[];
  shot: (shotId: string) => string;
  /** The novel page with this paragraph (0-based) in view. */
  para: (idx: number) => string;
}

/** A rewrite over the per-call cap or the episode's budget, waiting for the user's yes. */
export interface OverBudget {
  blockId: string;
  model: string | undefined;
  message: string;
}

/** A dubbed line: play it, and how long it runs. */
function LineAudio({ line, className }: { line: DubLine | undefined; className?: string }) {
  if (!line?.audio) return null;
  return (
    <AudioPlayer
      compact
      src={fileUrl(line.audio.sha256)}
      duration={line.audio.duration_s}
      label={line.text}
      className={className}
    />
  );
}

function BlockRow({
  block,
  selected,
  pending,
  rewriting,
  locked,
  confirmed,
  models,
  routeModel,
  overBudget,
  links,
  dub,
  onSelect,
  actions,
}: {
  block: Block;
  selected: boolean;
  pending: boolean;
  rewriting: boolean;
  locked: boolean;
  confirmed: boolean;
  models: readonly ModelOption[];
  routeModel: string | undefined;
  overBudget: OverBudget | null;
  links: ScriptLinks;
  dub: DubIndex;
  onSelect: () => void;
  actions: ScriptActions;
}) {
  const { t } = useTranslation("script");
  const text = useBlockText();
  const ids = useId();
  const [editing, setEditing] = useState<string | null>(null);
  const scene = block.kind === "scene";
  const shots = scene ? [] : links.shotsOf(block);
  const first = block.paras[0];
  const spoken = scene ? dub.scenes.get(block.id) : undefined;
  return (
    <li
      data-block={block.id}
      className={cn(
        "rounded-md border",
        selected ? "border-primary bg-tone-info-bg/40" : "border-transparent",
        !selected && (pending || block.edited) && "border-tone-warn-border",
        scene && !selected && "bg-muted",
      )}
    >
      <div className="flex items-start">
        <button
          type="button"
          aria-pressed={selected}
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-start gap-3 rounded-md px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className={cn("flex-1 text-[15px] leading-7", scene && "font-bold")}>
            {text.lead(block)}
            {block.text}
            {spoken?.lines ? (
              <span className="block text-xs leading-5 font-normal text-muted-foreground tabular-nums">
                {t("script.sceneSpoken", {
                  s: spoken.seconds.toFixed(1),
                  dubbed: spoken.dubbed,
                  lines: spoken.lines,
                })}
              </span>
            ) : null}
          </span>
          {block.kind !== "scene" && block.line.cliffhanger ? (
            <StatusBadge tone="info" icon={null} className="mt-1">
              {t("script.cliffhanger")}
            </StatusBadge>
          ) : null}
          <StatusBadge
            tone={text.flagged(block, pending) ? "warn" : "neutral"}
            icon={null}
            className="mt-1"
          >
            {text.prov(block, pending)}
          </StatusBadge>
        </button>
        {scene ? null : <LineAudio line={dub.lines.get(block.id)} className="py-1 pr-3" />}
      </div>
      {selected ? (
        <div className="flex flex-col gap-2 px-3 pb-3">
          {editing !== null ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`${ids}-edit`} className="text-xs font-normal text-muted-foreground">
                {t(confirmed ? "script.editLabel" : "script.editLabelDraft")}
              </Label>
              <Textarea
                id={`${ids}-edit`}
                rows={3}
                value={editing}
                onChange={(e) => setEditing(e.target.value)}
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={!editing.trim()}
                  onClick={() => {
                    actions.onSave(block, editing.trim());
                    setEditing(null);
                  }}
                >
                  {t("script.save")}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setEditing(null)}>
                  {t("script.cancel")}
                </Button>
              </div>
            </div>
          ) : overBudget ? (
            <div
              role="alert"
              className="flex flex-wrap items-center gap-2 rounded-md bg-tone-warn-bg px-3 py-2 text-sm text-tone-warn-fg"
            >
              <span>{overBudget.message}</span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                disabled={rewriting}
                onClick={() => actions.onRewrite(block, overBudget.model, true)}
              >
                {t("script.rewriteAnyway")}
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={locked}
                onClick={() => setEditing(block.text)}
              >
                <Pencil aria-hidden />
                {t("script.edit")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={locked || rewriting}
                onClick={() => actions.onRewrite(block)}
              >
                <RotateCw aria-hidden className={cn(rewriting && "animate-spin")} />
                {t(rewriting ? "script.rewriting" : "script.rewrite")}
              </Button>
              <ModelSwitchMenu
                options={models}
                currentKey={routeModel}
                align="start"
                onPick={(model) => actions.onRewrite(block, model)}
              >
                <Button size="sm" variant="outline" disabled={locked || rewriting}>
                  <ArrowLeftRight aria-hidden />
                  {t("script.rewriteWith")}
                </Button>
              </ModelSwitchMenu>
              {first !== undefined ? (
                <Link
                  to={links.para(first)}
                  className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                  title={t("script.inNovel")}
                >
                  {text.srcLabel(block)}
                </Link>
              ) : (
                <span className="text-xs text-muted-foreground">{text.srcLabel(block)}</span>
              )}
            </div>
          )}
          {!scene ? (
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <Clapperboard aria-hidden className="size-3.5" />
              <span>{t("script.shots")}</span>
              {shots.length ? (
                shots.map((s) => (
                  <Link
                    key={s.id}
                    to={links.shot(s.id)}
                    className="rounded-sm border px-1.5 py-0.5 font-mono text-foreground hover:border-primary hover:text-primary"
                    aria-label={t("script.shot", { label: s.label })}
                  >
                    {s.label}
                  </Link>
                ))
              ) : (
                <span>{t("script.noShots")}</span>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/** 剧本格式: the novel on the left (source paragraphs of the selected block lit), blocks right. */
export function ScriptScreenplay({
  blocks,
  paragraphs,
  selectedId,
  pendingId,
  rewritingId,
  locked,
  confirmed,
  models,
  routeModel,
  overBudget,
  links,
  dub,
  onSelect,
  actions,
}: {
  blocks: Block[];
  /** Novel paragraphs with the adopted additions merged in. */
  paragraphs: string[];
  selectedId: string | null;
  pendingId: string | null;
  rewritingId: string | null;
  /** A change is waiting in the impact dialog: no other edits until it is resolved. */
  locked: boolean;
  /** The script gate is confirmed: an edit shows the impact first. */
  confirmed: boolean;
  models: readonly ModelOption[];
  routeModel: string | undefined;
  overBudget: OverBudget | null;
  links: ScriptLinks;
  dub: DubIndex;
  onSelect: (id: string) => void;
  actions: ScriptActions;
}) {
  const { t } = useTranslation("script");
  const lit = new Set(blocks.find((b) => b.id === selectedId)?.paras ?? []);
  return (
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <section
        aria-label={t("script.source")}
        className="flex flex-col gap-1 rounded-lg border bg-card p-3.5"
      >
        <div className="mb-1 text-xs text-muted-foreground">{t("script.source")}</div>
        <ol className="flex flex-col gap-1">
          {paragraphs.map((text, i) => (
            <li
              key={i}
              data-lit={lit.has(i) || undefined}
              className={cn(
                "flex gap-2.5 rounded-md border border-transparent px-2 py-1.5 text-sm leading-7",
                lit.has(i) && "border-tone-info-border bg-tone-info-bg/50",
              )}
            >
              <span className="w-5 shrink-0 pt-0.5 font-mono text-xs text-muted-foreground">
                {String(i + 1).padStart(2, "0")}
              </span>
              <p>{text}</p>
            </li>
          ))}
        </ol>
      </section>
      <section aria-label={t("title")} className="rounded-lg border bg-card p-2">
        <ol className="flex flex-col gap-1">
          {blocks.map((b) => (
            <BlockRow
              key={b.id}
              block={b}
              selected={b.id === selectedId}
              pending={b.id === pendingId}
              rewriting={b.id === rewritingId}
              locked={locked}
              confirmed={confirmed}
              models={models}
              routeModel={routeModel}
              overBudget={overBudget?.blockId === b.id ? overBudget : null}
              links={links}
              dub={dub}
              onSelect={() => onSelect(b.id)}
              actions={actions}
            />
          ))}
        </ol>
      </section>
    </div>
  );
}

/** 结构化表格: lines only (no scene headings), one row each. */
export function ScriptTable({
  blocks,
  selectedId,
  pendingId,
  dub,
}: {
  blocks: Block[];
  selectedId: string | null;
  pendingId: string | null;
  dub: DubIndex;
}) {
  const { t } = useTranslation("script");
  const { t: te } = useTranslation("enums");
  const text = useBlockText();
  const lines = blocks.filter((b) => b.kind !== "scene");
  return (
    <div className="overflow-x-auto rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            {(["no", "type", "text", "who", "mood", "duration", "source"] as const).map((c) => (
              <TableHead key={c}>{t(`script.col.${c}`)}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {lines.map((b, i) => {
            const l = b.line;
            const spoken = b.kind === "dialogue" || b.kind === "vo";
            const pending = b.id === pendingId;
            const dubbed = dub.lines.get(b.id);
            return (
              <TableRow key={b.id} data-state={b.id === selectedId ? "selected" : undefined}>
                <TableCell className="font-mono text-xs">
                  {String(i + 1).padStart(2, "0")}
                </TableCell>
                <TableCell className="whitespace-nowrap">{te(`lineType.${b.kind}`)}</TableCell>
                <TableCell className="min-w-64 whitespace-normal">{b.text}</TableCell>
                <TableCell className="whitespace-nowrap">
                  {l.character_name ?? t("script.none")}
                </TableCell>
                <TableCell>{(spoken ? l.tone : l.mood) ?? t("script.none")}</TableCell>
                <TableCell className="whitespace-nowrap">
                  {dubbed?.audio ? (
                    <div className="flex items-center gap-2">
                      <LineAudio line={dubbed} />
                      {l.overlay_shot ? (
                        <span>{t("script.overlay", { shot: l.overlay_shot })}</span>
                      ) : null}
                    </div>
                  ) : l.overlay_shot ? (
                    t("script.overlay", { shot: l.overlay_shot })
                  ) : l.duration_s !== null ? (
                    t("script.seconds", { n: l.duration_s })
                  ) : (
                    t("script.none")
                  )}
                </TableCell>
                <TableCell
                  className={cn(
                    "whitespace-nowrap",
                    text.flagged(b, pending) ? "text-tone-warn-fg" : "text-muted-foreground",
                  )}
                >
                  {text.prov(b, pending)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
