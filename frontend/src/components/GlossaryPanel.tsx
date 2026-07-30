"use client";

import type { GlossaryTerm, Section } from "@/lib/api";
import { getContextSnippet } from "@/lib/glossaryContext";
import { formatTimestamp } from "@/lib/format";

type GlossaryPanelProps = {
  terms: GlossaryTerm[];
  activeTermId: string | null;
  onSelect: (id: string | null) => void;
  focusedSection: Section | null;
  showAllTerms: boolean;
  onToggleShowAll: () => void;
  firstUseTimeFor?: (termId: string) => number | null;
  onJumpToFirstUse?: (termId: string) => void;
};

export function GlossaryPanel({
  terms,
  activeTermId,
  onSelect,
  focusedSection,
  showAllTerms,
  onToggleShowAll,
  firstUseTimeFor,
  onJumpToFirstUse,
}: GlossaryPanelProps) {
  const active = terms.find((t) => t.id === activeTermId);
  const contextSnippet =
    active && focusedSection ? getContextSnippet(active, focusedSection) : null;

  return (
    <div className="rounded-2xl border border-ink-200 bg-white">
      <div className="border-b border-ink-100 bg-gradient-to-r from-fuchsia-50 to-pink-50 px-4 py-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-fuchsia-600">
          ✦ Beginner glossary
        </h3>
        {focusedSection && !showAllTerms ? (
          <p className="mt-1 text-xs text-ink-500">
            Terms for: <span className="font-medium text-ink-700">{focusedSection.title}</span>
          </p>
        ) : (
          <p className="mt-1 text-xs text-ink-500">
            {terms.length} terms in this video
          </p>
        )}
        <button
          type="button"
          onClick={onToggleShowAll}
          className="mt-2 text-xs font-medium text-fuchsia-600 hover:underline"
        >
          {showAllTerms ? "Show section terms only" : "Show all video terms"}
        </button>
      </div>

      {active && (
        <div className="border-b border-fuchsia-100 bg-fuchsia-50/60 px-4 py-3">
          <p className="text-sm font-semibold text-fuchsia-900">{active.display}</p>
          {active.domain && (
            <p className="mt-0.5 text-xs uppercase tracking-wide text-ink-500">{active.domain}</p>
          )}
          <p className="mt-2 text-sm leading-relaxed text-ink-700">
            {active.definition_beginner}
          </p>
          {onJumpToFirstUse && firstUseTimeFor && firstUseTimeFor(active.id) != null && (
            <button
              type="button"
              onClick={() => onJumpToFirstUse(active.id)}
              className="mt-2 rounded-full bg-fuchsia-100 px-3 py-1 text-xs font-medium text-fuchsia-700 transition hover:bg-fuchsia-500 hover:text-white"
            >
              ▶ First mention at {formatTimestamp(firstUseTimeFor(active.id)!)}
            </button>
          )}
          {contextSnippet && (
            <p className="mt-3 rounded-lg bg-white/70 px-3 py-2 text-sm leading-relaxed text-ink-600">
              <span className="font-medium text-ink-800">In this section: </span>
              {contextSnippet}
            </p>
          )}
        </div>
      )}

      {!active && (
        <div className="border-b border-ink-100 px-4 py-3 text-sm text-ink-500">
          Expand a section or click a highlighted term to see its definition.
        </div>
      )}

      <ul className="max-h-64 overflow-y-auto p-2">
        {terms.map((term) => (
          <li key={term.id}>
            <button
              type="button"
              onClick={() => onSelect(activeTermId === term.id ? null : term.id)}
              className={`w-full rounded-lg px-2 py-2 text-left text-sm transition ${
                activeTermId === term.id
                  ? "bg-fuchsia-100 font-medium text-fuchsia-700"
                  : "hover:bg-fuchsia-50/60 text-ink-700"
              }`}
            >
              {term.display}
            </button>
          </li>
        ))}
        {terms.length === 0 && (
          <li className="px-2 py-3 text-sm text-ink-500">
            {focusedSection
              ? "No glossary terms matched this section yet."
              : "No jargon terms detected yet."}
          </li>
        )}
      </ul>
    </div>
  );
}
