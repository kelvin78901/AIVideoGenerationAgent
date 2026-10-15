import type { NovelParagraph } from "@/api/schemas/novel";
import type { Scene, Script, ScriptLine } from "@/api/schemas/script";

/** One row of the screenplay: a scene heading or a line, in reading order. */
export type Block =
  | { id: string; kind: "scene"; scene: Scene; text: string; paras: number[]; edited: boolean }
  | {
      id: string;
      kind: ScriptLine["type"];
      line: ScriptLine;
      text: string;
      paras: number[];
      edited: boolean;
    };

/** 0-based novel paragraphs a block's source spans fall in. */
function parasOf(spans: { start: number }[], paragraphs: NovelParagraph[]): number[] {
  const out = spans.flatMap((s) => {
    const p = paragraphs.find((x) => s.start >= x.start && s.start <= x.end);
    return p ? [p.idx] : [];
  });
  return [...new Set(out)].sort((a, b) => a - b);
}

export function scriptBlocks(script: Script, paragraphs: NovelParagraph[]): Block[] {
  return [...script.scenes]
    .sort((a, b) => a.idx - b.idx)
    .flatMap((scene) => [
      {
        id: scene.id,
        kind: "scene" as const,
        scene,
        text: scene.heading,
        paras: parasOf(scene.source_spans, paragraphs),
        edited: scene.edited,
      },
      ...script.lines
        .filter((l) => l.scene_id === scene.id)
        .sort((a, b) => a.idx - b.idx)
        .map((line) => ({
          id: line.id,
          kind: line.type,
          line,
          text: line.text,
          paras: parasOf(line.source_spans, paragraphs),
          edited: line.edited,
        })),
    ]);
}
