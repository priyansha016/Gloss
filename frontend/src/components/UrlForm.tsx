"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { isUserKeyRequired, pollJobUntilDone, submitVideo } from "@/lib/api";
import { ApiKeyModal } from "./ApiKeyModal";
import { KeyBadge } from "./KeyBadge";

// Query param, not a path segment: the frontend is a static export (see next.config.ts).
const docPath = (videoId: string) => `/doc/?id=${videoId}`;

export function UrlForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [forceReprocess, setForceReprocess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [keyModalOpen, setKeyModalOpen] = useState(false);
  // Non-null when a blocked submit opened the modal: that's the only case where
  // saving a key should immediately retry.
  const [blockedReason, setBlockedReason] = useState<string | null>(null);

  async function runSubmit(targetUrl: string) {
    setError(null);
    setNotice(null);
    setStatus(null);
    setLoading(true);

    try {
      const result = await submitVideo(targetUrl, forceReprocess);

      if (result.cached || result.status === "ready") {
        router.push(docPath(result.video_id));
        return;
      }

      if (!result.job_id) {
        router.push(docPath(result.video_id));
        return;
      }

      setStatus("Queued…");
      const job = await pollJobUntilDone(result.job_id, (j) => {
        if (j.state === "processing") {
          setStatus(j.progress ?? "Processing… (may take several minutes)");
        } else {
          setStatus("Queued…");
        }
      });

      if (job.video_status === "rejected") {
        setNotice(job.error ?? "This video isn't a tutorial or lecture, so Gloss can't build study notes from it.");
        setLoading(false);
        return;
      }

      if (job.video_status === "no_captions") {
        setError("This video has no captions available. We only process caption tracks.");
        setLoading(false);
        return;
      }

      if (job.state === "failed" || job.video_status === "failed") {
        setError(job.error ?? "Processing failed. Try again later.");
        setLoading(false);
        return;
      }

      router.push(docPath(result.video_id));
    } catch (err) {
      if (isUserKeyRequired(err)) {
        setBlockedReason("Gloss needs your own AI provider key to build this document.");
        setKeyModalOpen(true);
      } else {
        setError(err instanceof Error ? err.message : "Something went wrong");
      }
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    void runSubmit(url.trim());
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl">
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="url"
          required
          placeholder="Paste a YouTube lecture or tutorial URL…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={loading}
          className="flex-1 rounded-xl border border-ink-200 bg-white px-4 py-3 text-ink-900 shadow-sm outline-none ring-accent/60 transition focus:ring-2 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={loading || !url.trim()}
          className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-3 font-medium text-white shadow-md shadow-indigo-200 transition hover:from-indigo-700 hover:to-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Working…" : "Gloss it"}
        </button>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-ink-500">
        <input
          type="checkbox"
          checked={forceReprocess}
          onChange={(e) => setForceReprocess(e.target.checked)}
          disabled={loading}
        />
        Rebuild from scratch
        {forceReprocess && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
            skips the instant cache — takes minutes
          </span>
        )}
      </label>
      {status && <p className="mt-3 text-sm text-ink-500">{status}</p>}
      {notice && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {notice}
        </p>
      )}
      {error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}
      <div className="mt-3">
        <KeyBadge
          onManage={() => {
            setBlockedReason(null);
            setKeyModalOpen(true);
          }}
        />
      </div>
      <ApiKeyModal
        open={keyModalOpen}
        reason={blockedReason}
        onClose={() => setKeyModalOpen(false)}
        onSaved={() => {
          const retry = blockedReason !== null && url.trim();
          setBlockedReason(null);
          if (retry) void runSubmit(url.trim());
        }}
      />
    </form>
  );
}
