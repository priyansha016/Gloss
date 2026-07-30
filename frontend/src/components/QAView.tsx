"use client";

import { useState } from "react";
import type { QAItem } from "@/lib/api";

type Filter = "all" | "understanding" | "interview";

export function QAView({ qa }: { qa: QAItem[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  if (!qa.length) {
    return <p className="text-sm text-ink-500">No questions were generated for this video.</p>;
  }
  const shown = qa.filter((q) => filter === "all" || q.kind === filter);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-ink-500">Test your understanding:</span>
        {(
          [
            { f: "all" as Filter, on: "bg-gradient-to-r from-amber-500 to-orange-500 text-white" },
            { f: "understanding" as Filter, on: "bg-sky-500 text-white" },
            { f: "interview" as Filter, on: "bg-amber-500 text-white" },
          ]
        ).map(({ f, on }) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${
              filter === f ? on : "bg-ink-100 text-ink-700 hover:bg-amber-50"
            }`}
          >
            {f}
          </button>
        ))}
      </div>
      {shown.map((item, i) => (
        <QACard key={i} item={item} />
      ))}
    </div>
  );
}

function QACard({ item }: { item: QAItem }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl border border-ink-200 bg-white p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-3 text-left"
      >
        <span
          className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            item.kind === "interview" ? "bg-amber-100 text-amber-700" : "bg-sky-100 text-sky-700"
          }`}
        >
          {item.kind}
        </span>
        <span className="flex-1 font-medium text-ink-900">{item.question}</span>
        <span className="shrink-0 text-sm text-ink-400">{open ? "−" : "+"}</span>
      </button>
      {open && <p className="mt-3 pl-14 leading-relaxed text-ink-600">{item.answer}</p>}
    </div>
  );
}
