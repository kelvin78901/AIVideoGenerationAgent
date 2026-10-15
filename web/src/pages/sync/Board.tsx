/**
 * The episode's ComfyUI asset board as ComfyUI will draw it (prototype Sync.dc.html):
 * groups, nodes and wires at the positions the backend writes into the workflow. Like media
 * frames, the canvas is dark in both themes; its colours imitate ComfyUI, not our tokens.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Message } from "@/api/schemas/common";
import type { BoardNode, PortType, SyncBoard } from "@/api/schemas/sync";
import { cn } from "@/lib/utils";

/** ComfyUI-like link colours per data type. */
const PORT: Record<PortType, string> = {
  image: "#7FD77F",
  audio: "#9DBBFF",
  prompt: "#F2C266",
  size: "#C9A0FF",
  video: "#FF9F7A",
};
const TONE: Record<NonNullable<BoardNode["tone"]>, string> = {
  ok: "#7FD77F",
  pending: "#F2C266",
  running: "#9DBBFF",
  waiting: "#A9ABA6",
};
/** Placeholder thumbnails until real files exist (M3). */
const SHADE = [
  "#2B2D31",
  "linear-gradient(160deg,#5B6270,#2E3138)",
  "linear-gradient(160deg,#4E5A52,#262B28)",
  "linear-gradient(160deg,#6A4848,#2A2224)",
  "linear-gradient(160deg,#4A4F66,#22242C)",
];
/** Static waveform for audio nodes. */
const BARS = [6, 10, 14, 9, 16, 12, 18, 8, 13, 17, 11, 6, 9, 15, 18, 12, 7, 10, 14, 16, 9, 12, 6];

const TITLE_H = 20;
const ROW_H = 18;
const rowY = (n: BoardNode, i: number) => n.y + TITLE_H + 4 + i * ROW_H + ROW_H / 2;

function tint(hex: string, alpha: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

export function Board({ board, defaultNode }: { board: SyncBoard; defaultNode?: string }) {
  const { t } = useTranslation("sync");
  const [picked, setPicked] = useState(defaultNode ?? board.nodes[0]?.id);
  const msg = (m: Message, scope: "group" | "caption") =>
    t(`board.${scope}.${m.code}` as "board.group.cast", { ...m.params, defaultValue: m.code });
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const sel = byId.get(picked ?? "") ?? board.nodes[0];

  return (
    <>
      <div className="overflow-x-auto rounded-lg">
        <div
          role="group"
          aria-label={t("board.label")}
          className="relative"
          style={{
            width: board.width,
            height: board.height,
            backgroundColor: "#1E1F22",
            backgroundImage: "radial-gradient(#34363B 1px, transparent 1px)",
            backgroundSize: "20px 20px",
          }}
        >
          {board.groups.map((g) => (
            <div
              key={g.id}
              className="absolute rounded-md"
              style={{
                left: g.x,
                top: g.y,
                width: g.w,
                height: g.h,
                background: tint(g.color, 0.16),
                border: `1px solid ${g.color}`,
              }}
            >
              <div
                className="flex h-6.5 items-center rounded-t-[5px] px-2.5 text-xs font-bold text-white"
                style={{ background: g.color }}
              >
                {msg(g.title, "group")}
              </div>
            </div>
          ))}

          <svg
            aria-hidden
            width={board.width}
            height={board.height}
            className="pointer-events-none absolute inset-0"
          >
            {board.wires.map((w, i) => {
              const a = byId.get(w.from.node);
              const b = byId.get(w.to.node);
              if (!a || !b) return null;
              const [x1, y1] = [a.x + a.w - 8, rowY(a, w.from.row)];
              const [x2, y2] = [b.x + 8, rowY(b, w.to.row)];
              return (
                <path
                  key={i}
                  d={`M${x1} ${y1} C${x1 + 20} ${y1} ${x2 - 20} ${y2} ${x2} ${y2}`}
                  fill="none"
                  stroke={PORT[w.type]}
                  strokeWidth={2}
                />
              );
            })}
          </svg>

          {board.nodes.map((n) => {
            const caption = n.caption ? msg(n.caption, "caption") : null;
            const on = n.id === sel?.id;
            return (
              <button
                key={n.id}
                type="button"
                aria-pressed={on}
                aria-label={caption ? t("board.node", { title: n.title, caption }) : n.title}
                onClick={() => setPicked(n.id)}
                className={cn(
                  "absolute flex flex-col overflow-hidden rounded-md text-left text-[#E6E6E3] outline-none focus-visible:ring-2 focus-visible:ring-[#8FB3FF]",
                  on ? "border-2 border-[#8FB3FF]" : "border border-[#45484E]",
                )}
                style={{ left: n.x, top: n.y, width: n.w, height: n.h, background: "#2B2D31" }}
              >
                <span className="flex h-5 shrink-0 items-center truncate bg-[#36393F] px-1.5 text-[11px]">
                  {n.title}
                </span>
                {n.thumb ? (
                  <span className="flex flex-col items-center gap-1 px-1 pt-1.5">
                    <span
                      className="block rounded-[3px]"
                      style={{
                        width: n.thumb.small ? 56 : 72,
                        height: n.thumb.small ? 100 : 128,
                        background: SHADE[n.thumb.shade] ?? SHADE[0],
                        border: n.thumb.dashed ? "1px dashed #6A6D72" : undefined,
                      }}
                    />
                    {caption ? (
                      <span
                        className="text-center text-[10px] leading-snug"
                        style={{ color: n.tone ? TONE[n.tone] : "#C9CAC6" }}
                      >
                        {caption}
                      </span>
                    ) : null}
                  </span>
                ) : null}
                {n.kind === "audio" ? (
                  <span className="flex h-5.5 items-center gap-0.5 px-2">
                    {BARS.map((h, i) => (
                      <span
                        key={i}
                        className="w-[3px] rounded-[1px] bg-[#8FB3FF]"
                        style={{ height: h }}
                      />
                    ))}
                  </span>
                ) : null}
                {n.text ? (
                  <span className="px-2 py-1 text-[10px] leading-normal text-[#C9CAC6]">
                    {n.text}
                  </span>
                ) : null}
                {n.rows.length ? (
                  <span className="flex flex-col py-1">
                    {n.rows.map((r, i) => (
                      <span
                        key={i}
                        className={cn(
                          "flex h-4.5 items-center gap-1.5 px-2 text-[10px]",
                          r.dir === "out" && "justify-end",
                          r.dir === "widget" ? "text-[#C9CAC6]" : "text-[#E6E6E3]",
                        )}
                      >
                        {r.dir === "in" ? <Port type={r.type} side="in" /> : null}
                        <span>{r.label}</span>
                        {r.dir === "out" ? <Port type={r.type} side="out" /> : null}
                      </span>
                    ))}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
      {sel ? (
        <div
          role="status"
          className="flex flex-wrap gap-x-4.5 gap-y-1.5 rounded-lg bg-muted/60 px-3.5 py-3 text-[13px] leading-relaxed"
        >
          <span className="font-bold">{sel.title}</span>
          {sel.facts.map((f) => (
            <span key={f.key}>
              <span className="text-muted-foreground">
                {t(`board.fact.${f.key}` as "board.fact.file", { defaultValue: f.key })}
              </span>{" "}
              {f.value}
            </span>
          ))}
        </div>
      ) : null}
    </>
  );
}

function Port({ type, side }: { type: PortType | null; side: "in" | "out" }) {
  return (
    <span
      className={cn("block size-2 rounded-full", side === "in" ? "-ml-1" : "-mr-1")}
      style={{ background: type ? PORT[type] : "#6A6D72" }}
    />
  );
}
