"use client";

import { useEffect, useState } from "react";
import {
  PROVIDERS,
  ProviderId,
  clearKey,
  loadKey,
  maskKey,
  saveKey,
} from "@/lib/llmKey";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Set when the modal was opened by a blocked request, so we can say why. */
  reason?: string | null;
  onSaved?: () => void;
};

export function ApiKeyModal({ open, onClose, reason, onSaved }: Props) {
  const [provider, setProvider] = useState<ProviderId>("groq");
  const [key, setKey] = useState("");
  const [existing, setExisting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prefixWarned, setPrefixWarned] = useState(false);

  useEffect(() => {
    if (!open) return;
    const stored = loadKey();
    setExisting(stored ? maskKey(stored.key) : null);
    setProvider(stored?.provider ?? "groq");
    setKey("");
    setError(null);
    setPrefixWarned(false);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [open, onClose]);

  if (!open) return null;

  const active = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0];

  function handleSave(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = key.trim();
    if (!trimmed) {
      setError("Paste your key first.");
      return;
    }
    // Prefix mismatch usually means the wrong provider was picked, but prefixes do
    // change — warn once, then let a second click through.
    if (!trimmed.startsWith(active.keyPrefix) && !prefixWarned) {
      setError(
        `That doesn't look like a ${active.label} key — those start with "${active.keyPrefix}". Check the provider above, or click Save again to use it anyway.`,
      );
      setPrefixWarned(true);
      return;
    }
    saveKey({ provider, key: trimmed });
    onSaved?.();
    onClose();
  }

  function handleRemove() {
    clearKey();
    setExisting(null);
    setKey("");
    onSaved?.();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-ink-900">Use your own AI key</h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-500">
            {reason ??
              "Gloss runs on your own AI provider key, so you keep your own free quota."}{" "}
            The key stays in this browser and is sent only with your own requests — it&apos;s
            never stored on the server.
          </p>
        </div>

        {existing && (
          <div className="mb-4 flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm">
            <span className="text-emerald-800">
              Saved key: <span className="font-mono">{existing}</span>
            </span>
            <button
              type="button"
              onClick={handleRemove}
              className="font-medium text-emerald-700 underline hover:text-emerald-900"
            >
              Remove
            </button>
          </div>
        )}

        <form onSubmit={handleSave}>
          <div className="mb-3 grid gap-2 sm:grid-cols-3">
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  setProvider(p.id);
                  setError(null);
                  setPrefixWarned(false);
                }}
                className={`rounded-xl border px-3 py-2 text-left transition ${
                  p.id === provider
                    ? "border-indigo-400 bg-indigo-50 ring-2 ring-indigo-200"
                    : "border-ink-200 hover:border-ink-300"
                }`}
              >
                <span className="block text-sm font-medium text-ink-900">{p.label}</span>
                <span className="block text-xs text-ink-500">
                  {p.free ? "Free tier" : "Paid"}
                </span>
              </button>
            ))}
          </div>

          <p className="mb-3 text-sm text-ink-500">
            {active.hint}{" "}
            <a
              href={active.consoleUrl}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-indigo-600 underline hover:text-indigo-800"
            >
              Get a {active.label} key →
            </a>
          </p>

          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder={`${active.keyPrefix}…`}
            value={key}
            onChange={(e) => {
              setKey(e.target.value);
              setError(null);
            }}
            className="w-full rounded-xl border border-ink-200 bg-white px-4 py-3 font-mono text-sm text-ink-900 outline-none ring-accent/60 transition focus:ring-2"
          />

          {error && (
            <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{error}</p>
          )}

          <div className="mt-4 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl px-4 py-2 text-sm font-medium text-ink-500 hover:text-ink-900"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-2 font-medium text-white shadow-md shadow-indigo-200 transition hover:from-indigo-700 hover:to-violet-700"
            >
              Save key
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
