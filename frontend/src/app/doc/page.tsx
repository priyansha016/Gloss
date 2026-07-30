"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { StudyDoc } from "@/components/StudyDoc";
import { getVideo, type VideoDocument } from "@/lib/api";

const PENDING_STATUSES = new Set(["queued", "processing"]);
const POLL_MS = 3000;

// The doc id is a query param, not a route segment: a static export can't
// pre-render /doc/[id] for ids that don't exist yet at build time.
function DocView() {
  const videoId = useSearchParams().get("id") ?? "";
  const [doc, setDoc] = useState<VideoDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    if (!videoId) {
      setError("No document id in the link — head back and submit a video.");
      setLoading(false);
      return;
    }

    async function load() {
      try {
        const data = await getVideo(videoId);
        if (cancelled) return;
        setDoc(data);
        setLoading(false);
        if (PENDING_STATUSES.has(data.status)) {
          // Keep polling until the worker finishes, then the doc renders itself.
          timer = setTimeout(load, POLL_MS);
        } else if (data.status === "rejected") {
          setError(
            data.status_reason ??
              "This video isn't a tutorial or lecture, so Gloss can't build study notes from it.",
          );
        } else if (data.status === "no_captions") {
          setError("This video has no captions available. Gloss only processes caption tracks.");
        } else if (data.status === "failed") {
          setError(data.status_reason ?? "Processing failed. Resubmit the video from the home page to retry.");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load document");
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [videoId]);

  const pending = doc != null && PENDING_STATUSES.has(doc.status);

  return (
    <>
      {loading && <p className="mx-auto max-w-7xl text-ink-500">Loading study document…</p>}

      {pending && (
        <div className="mx-auto max-w-xl rounded-2xl border border-ink-200 bg-white p-8 text-center shadow-sm">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-accent-soft border-t-accent" />
          <h2 className="mb-1 font-semibold text-ink-900">Glossing this video…</h2>
          {doc?.progress && (
            <p className="mb-2 inline-block rounded-full bg-gradient-to-r from-indigo-50 to-violet-50 px-3 py-1 text-sm font-medium text-indigo-700">
              {doc.progress}
            </p>
          )}
          <p className="text-sm leading-relaxed text-ink-500">
            A long video can take several minutes — this page updates automatically.
          </p>
        </div>
      )}

      {error && !loading && !pending && (
        <p className="mx-auto max-w-7xl rounded-xl bg-red-50 px-4 py-3 text-red-700">{error}</p>
      )}

      {doc && doc.status === "ready" && doc.status_reason && !loading && (
        <div className="mx-auto mb-6 max-w-7xl rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-900">
          <p className="font-medium">Reprocess didn&apos;t finish</p>
          <p className="mt-1 text-sm text-amber-800">
            {doc.status_reason} Showing your previous study notes.
          </p>
        </div>
      )}

      {doc && doc.status === "ready" && !loading && <StudyDoc doc={doc} />}
    </>
  );
}

export default function DocPage() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-indigo-50/70 via-ink-50 to-white px-6 py-10">
      <div className="mx-auto mb-8 max-w-7xl">
        <Link href="/" className="text-sm font-medium text-accent hover:underline">
          ← New video
        </Link>
      </div>
      <Suspense fallback={<p className="mx-auto max-w-7xl text-ink-500">Loading study document…</p>}>
        <DocView />
      </Suspense>
    </main>
  );
}
