import { useTranslation } from "react-i18next";

import type { Scene, Script, ScriptLine } from "@/api/schemas/script";

/**
 * One row of the screenplay: a scene heading or a line, in reading order. `text` is what an
 * edit changes (a heading without its 场号, which the backend counts); `paras` are the novel
 * paragraphs it comes from (0-based).
 */
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

export function scriptBlocks(script: Script): Block[] {
  return [...script.scenes]
    .sort((a, b) => a.idx - b.idx)
    .flatMap((scene) => [
      {
        id: scene.id,
        kind: "scene" as const,
        scene,
        text: scene.heading,
        paras: scene.paras,
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
          paras: line.paras,
          edited: line.edited,
        })),
    ]);
}

/** What a block is shown with: 「△ 」, 「林晚（低声）：」, 「场 2」 + the heading. */
export function useBlockLead() {
  const { t } = useTranslation("script");
  return (b: Block) => {
    if (b.kind === "scene") return t("script.sceneLead", { n: b.scene.idx });
    if (b.kind === "action") return t("script.actionMark");
    if (b.kind === "dialogue" || b.kind === "vo")
      return t("script.speaker", { who: b.line.character_name ?? "", tone: b.line.tone ?? "" });
    return "";
  };
}

/** The line uses an accepted addition (小说补全): its source has a `sug:` span. */
export function fromAddition(b: Block): boolean {
  return b.kind !== "scene" && b.line.source_spans.some((s) => s.source_id.startsWith("sug:"));
}
