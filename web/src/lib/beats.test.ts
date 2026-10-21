import type { Episode } from "@/api/schemas/episodes";
import { formatEmotion, patchBeat } from "@/lib/beats";

const beat = (id: string, episode_id: string, idx: number) => ({
  id,
  episode_id,
  idx,
  text: id,
  emotion: 0,
  paras: [],
  source_spans: [],
});

const plan = (): Episode[] =>
  [
    ["e1", ["a", "b", "c"]],
    ["e2", ["d"]],
  ].map(([id, beats], i) => ({
    id: id as string,
    series_id: "s",
    idx: i + 1,
    title: "",
    hook: null,
    cliffhanger: null,
    target_seconds: null,
    scene_count: null,
    budget_usd: null,
    stage: "script_pending",
    scene_from: null,
    scene_to: null,
    shot_count: null,
    script_status: "none",
    beats: (beats as string[]).map((b, j) => beat(b, id as string, j + 1)),
  }));

const shape = (list: Episode[]) => list.map((e) => e.beats.map((b) => `${b.id}${b.idx}`));

describe("patchBeat", () => {
  it("moves a beat among the target episode's other beats and renumbers", () => {
    expect(shape(patchBeat(plan(), "a", { episode_id: "e2", position: 0 }))).toEqual([
      ["b1", "c2"],
      ["a1", "d2"],
    ]);
    expect(shape(patchBeat(plan(), "a", { position: 2 }))).toEqual([["b1", "c2", "a3"], ["d1"]]);
    expect(shape(patchBeat(plan(), "c", { episode_id: "e2" }))).toEqual([
      ["a1", "b2"],
      ["d1", "c2"],
    ]);
    const moved = patchBeat(plan(), "c", { episode_id: "e2" });
    expect(moved[1]?.beats[1]?.episode_id).toBe("e2");
  });

  it("changes text and emotion; unknown ids change nothing", () => {
    const out = patchBeat(plan(), "b", { text: " 新 ", emotion: -0.5 });
    expect(out[0]?.beats[1]).toMatchObject({ text: "新", emotion: -0.5 });
    const before = plan();
    expect(patchBeat(before, "nope", { text: "x" })).toBe(before);
    expect(patchBeat(before, "a", { episode_id: "nope" })).toBe(before);
  });
});

describe("formatEmotion", () => {
  it("signs and trims", () => {
    expect([0.4, -0.25, 0, 1, -1, 0.004].map(formatEmotion)).toEqual([
      "+0.4",
      "−0.25",
      "0",
      "+1",
      "−1",
      "0",
    ]);
  });
});
