import type React from "react";
import { parseTimestampLabel } from "@/lib/format";
import { highlightGlossaryTerms } from "@/lib/glossaryHighlight";

const TLDR_LINE = /^- \[(\d{1,2}(?::\d{2}){1,2})\]\s*(.+?):\s*(.+)$/;

export function renderTldr(
  tldr: string,
  glossaryTerms: { id: string; display: string }[],
  activeTermId: string | null,
  onSelectTerm: (id: string | null) => void,
  onJump: (seconds: number) => void,
): React.ReactNode {
  const lines = tldr.split("\n").filter((line) => line.trim());

  return (
    <div className="space-y-2">
      {lines.map((line, i) => {
        const match = line.match(TLDR_LINE);
        if (!match) {
          return (
            <p key={i} className="leading-relaxed text-ink-700">
              {highlightGlossaryTerms(line, glossaryTerms, activeTermId, onSelectTerm)}
            </p>
          );
        }

        const [, tsLabel, title, summary] = match;
        const seconds = parseTimestampLabel(tsLabel);

        return (
          <p key={i} className="leading-relaxed text-ink-700">
            <button
              type="button"
              onClick={() => onJump(seconds)}
              className="mr-1 font-mono text-xs font-medium text-accent hover:underline"
            >
              [{tsLabel}]
            </button>
            <span className="font-medium text-ink-900">{title}:</span>{" "}
            {highlightGlossaryTerms(summary, glossaryTerms, activeTermId, onSelectTerm)}
          </p>
        );
      })}
    </div>
  );
}
