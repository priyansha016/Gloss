"use client";

import { useState } from "react";
import type { Command } from "@/lib/api";

export function CommandsBlock({ commands }: { commands: Command[] }) {
  const [open, setOpen] = useState(false);
  if (!commands.length) return null;
  return (
    <div className="overflow-hidden rounded-xl border border-emerald-200/70 bg-emerald-50/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="text-sm font-bold uppercase tracking-wide text-emerald-800">
          ⌘ Commands cheat-sheet
          <span className="ml-2 rounded-full bg-emerald-200 px-2 py-0.5 text-xs font-semibold text-emerald-800">
            {commands.length}
          </span>
        </span>
        <span className="text-xs font-medium text-emerald-500">{open ? "▲ hide" : "▼ show"}</span>
      </button>
      {open && (
        <div className="space-y-2 px-4 pb-3">
          {commands.map((c, i) => (
            <CommandRow key={i} command={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function CommandRow({ command }: { command: Command }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="group flex items-start justify-between gap-3 rounded-lg bg-ink-900 px-3 py-2">
      <div className="min-w-0">
        <code className="block break-all text-xs leading-relaxed text-ink-50">{command.cmd}</code>
        {command.purpose && <p className="mt-1 text-xs text-ink-200/80">{command.purpose}</p>}
      </div>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard?.writeText(command.cmd);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        }}
        className="shrink-0 rounded px-2 py-1 text-xs text-ink-200 transition hover:bg-white/10"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
