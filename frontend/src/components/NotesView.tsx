"use client";

import type { NoteGroup } from "@/lib/api";

export function NotesView({ notes }: { notes: NoteGroup[] }) {
  if (!notes.length) {
    return <p className="text-sm text-ink-500">No notes were generated for this video.</p>;
  }
  return (
    <div className="space-y-6">
      <p className="text-sm text-ink-500">
        Study notes — the way you&rsquo;d jot them down while watching.
      </p>
      {notes.map((group, i) => (
        <div key={i} className="rounded-2xl border border-ink-200 border-l-4 border-l-emerald-400 bg-white p-5">
          <h3 className="mb-2 font-semibold text-emerald-900">{group.heading}</h3>
          <ul className="space-y-1.5">
            {group.bullets.map((b, j) => (
              <li key={j} className="flex gap-2 leading-relaxed text-ink-700">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
