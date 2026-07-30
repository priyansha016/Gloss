"use client";

import { useEffect, useRef, useState } from "react";
import { askQuestion, isUserKeyRequired, type AskSource, type AskTurn } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { ApiKeyModal } from "./ApiKeyModal";

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; sources: AskSource[] }
  | { role: "error"; text: string };

const FALLBACK_SUGGESTIONS = [
  "Explain this like I'm completely new to the topic",
  "What are the most important things to remember?",
];

function loadHistory(videoId: string): Message[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(`gloss-chat-${videoId}`) ?? "[]");
  } catch {
    return [];
  }
}

export function ChatPanel({
  videoId,
  onJump,
  suggestions,
}: {
  videoId: string;
  onJump: (seconds: number) => void;
  suggestions?: string[];
}) {
  const [messages, setMessages] = useState<Message[]>(() => loadHistory(videoId));
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [needsKey, setNeedsKey] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const starters = suggestions?.length ? suggestions : FALLBACK_SUGGESTIONS;

  // Persist chat per video so it survives reloads (capped to the last 40 messages).
  useEffect(() => {
    try {
      localStorage.setItem(`gloss-chat-${videoId}`, JSON.stringify(messages.slice(-40)));
    } catch {
      /* storage full/unavailable — chat still works, just not persisted */
    }
  }, [messages, videoId]);

  const send = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    // Prior turns (excluding errors) give the model context for follow-ups.
    const history: AskTurn[] = messages
      .filter((m): m is Exclude<Message, { role: "error"; text: string }> => m.role !== "error")
      .map((m) => ({ role: m.role, content: m.text }));
    setMessages((m) => [...m, { role: "user", text: q }]);
    try {
      const res = await askQuestion(videoId, q, history);
      setMessages((m) => [...m, { role: "assistant", text: res.answer, sources: res.sources }]);
    } catch (err) {
      if (isUserKeyRequired(err)) {
        setNeedsKey(true);
        return; // the finally block still clears `busy`
      }
      // apiFetch throws with the response body — surface the backend's detail if present.
      let text = "Couldn't get an answer — please try again.";
      if (err instanceof Error) {
        try {
          const detail = JSON.parse(err.message)?.detail;
          if (typeof detail === "string" && detail) text = detail;
        } catch {
          /* not JSON — keep generic message */
        }
      }
      setMessages((m) => [...m, { role: "error", text }]);
    } finally {
      setBusy(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-teal-200 bg-white shadow-sm">
      <div className="flex items-start justify-between bg-gradient-to-r from-teal-500 to-cyan-600 px-5 py-3">
        <div>
          <h2 className="font-semibold text-white">✦ Ask this video</h2>
          <p className="text-xs text-teal-50/90">
            Answers come from the video&rsquo;s own notes and transcript, with timestamps.
          </p>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={() => setMessages([])}
            className="mr-6 mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs text-white/70 transition hover:bg-white/20 hover:text-white"
          >
            Clear
          </button>
        )}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-ink-500">Try one of these:</p>
            {starters.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                className="block w-full rounded-xl border border-ink-200 px-3 py-2 text-left text-sm text-ink-700 transition hover:border-teal-400 hover:text-teal-700"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => {
          if (msg.role === "user") {
            return (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm leading-relaxed text-white">
                  {msg.text}
                </p>
              </div>
            );
          }
          if (msg.role === "error") {
            return (
              <p key={i} className="rounded-xl bg-red-50 px-4 py-2.5 text-sm text-red-700">
                {msg.text}
              </p>
            );
          }
          return (
            <div key={i} className="max-w-[92%] space-y-2">
              <p className="whitespace-pre-wrap rounded-2xl rounded-bl-md bg-ink-50 px-4 py-2.5 text-sm leading-relaxed text-ink-800">
                {msg.text}
              </p>
              {msg.sources.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pl-1">
                  {msg.sources.map((src, j) => (
                    <button
                      key={j}
                      type="button"
                      onClick={() => onJump(src.start_s)}
                      className="rounded-full bg-sky-100 px-2.5 py-1 text-xs font-medium text-sky-700 transition hover:bg-sky-500 hover:text-white"
                      title={`Jump to ${src.title}`}
                    >
                      ▶ {formatTimestamp(src.start_s)} {src.title.length > 28 ? `${src.title.slice(0, 28)}…` : src.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {busy && (
          <div className="flex items-center gap-2 text-sm text-ink-400">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-200 border-t-teal-500" />
            Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <ApiKeyModal
        open={needsKey}
        reason="Answering questions runs on your own AI provider key."
        onClose={() => setNeedsKey(false)}
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex gap-2 border-t border-ink-100 p-3"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about this video…"
          disabled={busy}
          className="flex-1 rounded-xl border border-ink-200 px-4 py-2.5 text-sm text-ink-900 outline-none ring-teal-400/60 focus:ring-2 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-xl bg-gradient-to-r from-teal-500 to-cyan-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm shadow-teal-200 transition hover:from-teal-600 hover:to-cyan-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
