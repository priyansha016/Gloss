"use client";

import { useEffect, useState } from "react";
import { StoredKey, loadKey, maskKey, providerInfo, subscribeToKey } from "@/lib/llmKey";

/** Inline "using your own key / add a key" control. */
export function KeyBadge({ onManage }: { onManage: () => void }) {
  const [stored, setStored] = useState<StoredKey | null>(null);
  // Read after mount: localStorage doesn't exist during the static build, and
  // rendering it on the server would mismatch the client.
  useEffect(() => {
    const sync = () => setStored(loadKey());
    sync();
    return subscribeToKey(sync);
  }, []);

  if (!stored) {
    return (
      <button
        type="button"
        onClick={onManage}
        className="text-sm text-ink-500 underline decoration-dotted underline-offset-4 transition hover:text-ink-900"
      >
        Use your own AI key
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onManage}
      className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs text-emerald-800 transition hover:border-emerald-300"
    >
      <span className="text-emerald-500">●</span>
      {providerInfo(stored.provider).label} key
      <span className="font-mono text-emerald-700">{maskKey(stored.key)}</span>
    </button>
  );
}
