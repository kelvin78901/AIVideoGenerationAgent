/**
 * 全剧情绪曲线: every beat of the plan in order, its emotion from -1 to 1 (SPEC 11.3: hand-drawn
 * SVG, one y axis, 2px line, ≥ 8px points, crosshair + readout, 图 / 表 switch). Dashed lines
 * separate the episodes; their names sit under the plot.
 */
import { curveMonotoneX, line } from "d3-shape";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Episode } from "@/api/schemas/episodes";
import { XLabels, YGrid } from "@/components/charts/axis";
import { ChartCard, ChartTable, Readout } from "@/components/charts/ChartCard";
import { percentScale, pct } from "@/components/charts/scale";
import { formatEmotion } from "@/lib/beats";

const VB_W = 1000;
const VB_H = 300;
const MARGIN_LEFT = 36;
const MARGIN_RIGHT = 12;

interface Point {
  key: string;
  i: number;
  emotion: number;
  episode: Episode;
  idx: number;
  text: string;
}

export function EmotionCurve({ episodes }: { episodes: Episode[] }) {
  const { t } = useTranslation("script");
  const [hover, setHover] = useState<number | null>(null);
  const points: Point[] = episodes
    .flatMap((episode) => episode.beats.map((beat) => ({ episode, beat })))
    .map(({ episode, beat }, i) => ({
      key: beat.id,
      i,
      emotion: beat.emotion,
      episode,
      idx: beat.idx,
      text: beat.text,
    }));
  if (!points.length) return null;

  const x = percentScale([-0.5, points.length - 0.5]);
  const y = percentScale([-1, 1], true);
  const path =
    line<Point>()
      .x((p) => (x(p.i) / 100) * VB_W)
      .y((p) => (y(p.emotion) / 100) * VB_H)
      .curve(curveMonotoneX)(points) ?? "";
  // Episode i spans [first - 0.5, last + 0.5]; a dashed line between neighbours.
  const spans = episodes
    .filter((e) => e.beats.length)
    .map((e) => {
      const first = points.findIndex((p) => p.episode.id === e.id);
      return { episode: e, from: first - 0.5, to: first + e.beats.length - 0.5 };
    });
  const hovered = hover !== null ? points[hover] : undefined;
  const label = (p: Point) =>
    t("curve.point", {
      n: p.episode.idx,
      idx: p.idx,
      text: p.text,
      value: formatEmotion(p.emotion),
    });

  const chart = (
    <div>
      <div
        className="relative"
        style={{ height: 170, margin: `8px ${MARGIN_RIGHT}px 0 ${MARGIN_LEFT}px` }}
      >
        <YGrid
          ticks={[1, 0, -1].map((v) => ({ value: v, label: formatEmotion(v) }))}
          y={y}
          labelWidth={MARGIN_LEFT}
        />
        {spans.slice(1).map((s) => (
          <div
            key={s.episode.id}
            aria-hidden
            data-episode-rule
            className="absolute inset-y-0 border-l border-dashed border-chart-crosshair/60"
            style={{ left: pct(x(s.from)) }}
          />
        ))}
        <svg
          aria-hidden
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          preserveAspectRatio="none"
          className="absolute inset-0 size-full overflow-visible"
        >
          <path
            data-line
            d={path}
            fill="none"
            className="stroke-chart-1"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {hovered ? (
          <div
            aria-hidden
            data-crosshair
            className="absolute inset-y-0 w-px bg-chart-crosshair"
            style={{ left: pct(x(hovered.i)) }}
          />
        ) : null}
        {points.map((p) => (
          <div
            key={p.key}
            aria-hidden
            data-dot
            className={
              "pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-chart-1 ring-2 ring-card " +
              (hover === p.i ? "size-3" : "size-2.5")
            }
            style={{ left: pct(x(p.i)), top: pct(y(p.emotion)) }}
          />
        ))}
        {points.map((p) => (
          <button
            key={p.key}
            type="button"
            aria-label={label(p)}
            aria-pressed={hover === p.i}
            onPointerEnter={() => setHover(p.i)}
            onFocus={() => setHover(p.i)}
            onClick={() => setHover(p.i)}
            className="absolute inset-y-0 p-0 outline-none focus-visible:bg-accent/40"
            style={{ left: pct(x(p.i - 0.5)), width: pct(x(p.i + 0.5) - x(p.i - 0.5)) }}
          />
        ))}
      </div>
      <XLabels
        ticks={spans.map((s) => ({
          value: (s.from + s.to) / 2,
          label: t("curve.episode", { n: s.episode.idx }),
        }))}
        x={x}
        marginLeft={MARGIN_LEFT}
        marginRight={MARGIN_RIGHT}
      />
      <div className="mt-2">
        {hovered ? (
          <Readout title={t("curve.readout", { n: hovered.episode.idx, idx: hovered.idx })}>
            {t("curve.readoutText", { text: hovered.text, value: formatEmotion(hovered.emotion) })}
          </Readout>
        ) : (
          <div
            data-readout
            className="flex min-h-11 items-center rounded-lg bg-muted px-2.5 py-2 text-[13px] text-muted-foreground"
          >
            {t("curve.hint")}
          </div>
        )}
      </div>
    </div>
  );

  const table = (
    <ChartTable
      label={t("curve.table")}
      minWidth={480}
      columns={[
        { key: "episode", label: t("curve.col.episode"), className: "w-12" },
        { key: "beat", label: t("curve.col.beat"), className: "w-12" },
        { key: "text", label: t("curve.col.text") },
        { key: "emotion", label: t("curve.col.emotion"), className: "w-16 text-right" },
      ]}
      rows={points.map((p) => ({
        key: p.key,
        cells: [p.episode.idx, p.idx, p.text, formatEmotion(p.emotion)],
      }))}
    />
  );

  return (
    <ChartCard
      title={t("curve.title")}
      subtitle={t("curve.subtitle")}
      chart={chart}
      table={table}
      onPointerLeave={() => setHover(null)}
    />
  );
}
