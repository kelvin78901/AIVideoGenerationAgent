/** Beats of the episode plan (节拍看板, 情绪曲线): the move the board shows before the backend
 * answers, and how an emotion reads. */
import type { BeatPatch, Episode } from "@/api/schemas/episodes";

/**
 * The plan after `PATCH /beats/{id}` as the backend applies it (`episodes/ops.py:patch_beat`):
 * `position` is among the target episode's other beats (the end when omitted); everything is
 * renumbered. Unknown ids leave the plan as it is (the backend's error says why).
 */
export function patchBeat(list: Episode[], id: string, patch: BeatPatch): Episode[] {
  const next = structuredClone(list);
  const source = next.find((e) => e.beats.some((b) => b.id === id));
  const beat = source?.beats.find((b) => b.id === id);
  if (!source || !beat) return list;
  if (patch.text !== undefined && patch.text.trim()) beat.text = patch.text.trim();
  if (patch.emotion !== undefined) beat.emotion = patch.emotion;
  if (patch.episode_id !== undefined || patch.position !== undefined) {
    const target = patch.episode_id ? next.find((e) => e.id === patch.episode_id) : source;
    if (!target) return list;
    source.beats = source.beats.filter((b) => b.id !== id);
    const at = Math.min(patch.position ?? target.beats.length, target.beats.length);
    target.beats.splice(at, 0, beat);
  }
  for (const e of next)
    e.beats.forEach((b, i) => {
      b.idx = i + 1;
      b.episode_id = e.id;
    });
  return next;
}

/** 「+0.4」「−0.25」「0」: a sign and at most two decimals. */
export function formatEmotion(v: number): string {
  const abs = Math.abs(v)
    .toFixed(2)
    .replace(/\.?0+$/, "");
  if (abs === "0" || abs === "") return "0";
  return `${v > 0 ? "+" : "−"}${abs}`;
}
