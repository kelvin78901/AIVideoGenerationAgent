import { scaleLinear } from "d3-scale";

export interface Tick {
  value: number;
  label: string;
}

/** Linear scale to a percentage of the plot box (0–100). `invert` flips it for the y axis. */
export function percentScale([d0, d1]: [number, number], invert = false) {
  const s = scaleLinear()
    .domain([d0, d1])
    .range(invert ? [100, 0] : [0, 100]);
  return (v: number) => s(v);
}

export const pct = (v: number) => `${v.toFixed(2)}%`;

/** Clean y-axis ticks: a step from 1 / 2 / 4 / 5 × 10ⁿ, at most `count` intervals above zero. */
export function niceTicks(max: number, count = 3): { ticks: number[]; top: number } {
  if (!(max > 0)) return { ticks: [0, 1], top: 1 };
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 4, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const top = Math.ceil(max / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return { ticks, top };
}
