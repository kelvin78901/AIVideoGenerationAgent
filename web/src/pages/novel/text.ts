import type { Novel, Suggestion } from "@/api/schemas/novel";

/** Characters of the text as it will be used: the original plus adopted additions. */
export function charCount(novel: Novel, suggestions: Suggestion[]): number {
  const base = novel.paragraphs.reduce((n, p) => n + [...p.text].length, 0);
  return suggestions
    .filter((s) => s.status === "accepted")
    .reduce((n, s) => n + [...s.text].length, base);
}
