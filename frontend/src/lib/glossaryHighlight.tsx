import type React from "react";

export function highlightGlossaryTerms(
  text: string,
  terms: { id: string; display: string }[],
  activeTermId: string | null,
  onSelect: (id: string) => void,
  seen?: Set<string>,
): React.ReactNode[] {
  if (!text || terms.length === 0) return [text];

  const sorted = [...terms].sort((a, b) => b.display.length - a.display.length);
  const pattern = sorted
    .map((t) => t.display.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  if (!pattern) return [text];

  const re = new RegExp(`\\b(${pattern})\\b`, "gi");
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    const matched = match[0];
    const term = sorted.find((t) => t.display.toLowerCase() === matched.toLowerCase());
    // Dedupe: once a term is highlighted within a `seen` scope (e.g. one section),
    // later occurrences render as plain text instead of highlighting the same word 5×.
    if (term && seen) {
      if (seen.has(term.id)) {
        nodes.push(matched);
        last = match.index + matched.length;
        continue;
      }
      seen.add(term.id);
    }
    if (term) {
      nodes.push(
        <button
          key={`${term.id}-${match.index}`}
          type="button"
          onClick={() => onSelect(term.id)}
          className={`font-medium underline decoration-dotted underline-offset-2 ${
            activeTermId === term.id ? "text-accent bg-accent-soft rounded px-0.5" : "text-accent hover:bg-accent-soft rounded px-0.5"
          }`}
        >
          {matched}
        </button>,
      );
    } else {
      nodes.push(matched);
    }
    last = match.index + matched.length;
  }

  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}
