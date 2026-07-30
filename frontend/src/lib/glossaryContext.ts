import type { GlossaryTerm, Section, VideoDocument } from "@/lib/api";

const AMBIGUOUS_TERMS = new Set([
  "service",
  "node",
  "application",
  "component",
  "database",
  "config",
  "secret",
  "deployment",
  "cluster",
]);

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function termMentionedInText(text: string, display: string): boolean {
  if (!text || !display) return false;
  return new RegExp(`\\b${escapeRegExp(display)}\\b`, "i").test(text);
}

function occurrenceCount(sectionId: string, termId: string, doc: VideoDocument): number {
  return doc.term_occurrences.filter(
    (o) => o.section_id === sectionId && o.term_id === termId,
  ).length;
}

/** Terms relevant to a section: title/summary mentions rank above raw transcript hits. */
export function getSectionTerms(section: Section, doc: VideoDocument): GlossaryTerm[] {
  const summaryText = [section.title, section.summary_short, section.summary_full]
    .filter(Boolean)
    .join(" ");

  const scored = doc.glossary
    .map((term) => {
      const inTitle = termMentionedInText(section.title, term.display);
      const inSummary = termMentionedInText(summaryText, term.display);
      const inTranscript = occurrenceCount(section.id, term.id, doc) > 0;
      const ambiguous = AMBIGUOUS_TERMS.has(term.display.toLowerCase());

      let score = 0;
      if (inTitle) score += 100;
      if (inSummary) score += 50;
      if (inTranscript) score += 10;
      if (ambiguous && !inTitle && !inSummary) score -= 40;

      return { term, score, inTitle, inSummary };
    })
    .filter(({ score, inTitle, inSummary, term }) => {
      if (score <= 0) return false;
      const ambiguous = AMBIGUOUS_TERMS.has(term.display.toLowerCase());
      if (ambiguous && !inTitle && !inSummary) return false;
      return true;
    })
    .sort((a, b) => b.score - a.score || a.term.display.localeCompare(b.term.display));

  return scored.map(({ term }) => term);
}

export function getContextSnippet(term: GlossaryTerm, section: Section): string | null {
  const text = section.summary_full || section.summary_short || "";
  if (!text) return null;

  const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean);
  const match = sentences.find((sentence) =>
    termMentionedInText(sentence, term.display),
  );
  if (!match) return null;
  // Unpunctuated auto-captions can make one "sentence" thousands of chars long —
  // a snippet must stay a snippet.
  if (match.length <= 240) return match;
  const idx = match.toLowerCase().indexOf(term.display.toLowerCase());
  const start = Math.max(0, idx - 80);
  return `${start > 0 ? "…" : ""}${match.slice(start, start + 240).trimEnd()}…`;
}

export function pickDefaultTerm(terms: GlossaryTerm[]): string | null {
  return terms[0]?.id ?? null;
}
