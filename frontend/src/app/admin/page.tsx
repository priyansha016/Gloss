"use client";

import { useEffect, useState } from "react";
import {
  clearAdminKey,
  getAdminStats,
  loadAdminKey,
  saveAdminKey,
  type AdminStats,
} from "@/lib/api";

export default function AdminPage() {
  const [key, setKey] = useState("");
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const k = loadAdminKey();
    if (k) setSavedKey(k);
  }, []);

  useEffect(() => {
    if (!savedKey) return;
    setLoading(true);
    setError(null);
    getAdminStats(savedKey)
      .then(setStats)
      .catch(() => {
        setError("Invalid admin key or stats unavailable.");
        clearAdminKey();
        setSavedKey(null);
        setStats(null);
      })
      .finally(() => setLoading(false));
  }, [savedKey]);

  function unlock(e: React.FormEvent) {
    e.preventDefault();
    if (!key.trim()) return;
    saveAdminKey(key.trim());
    setSavedKey(key.trim());
    setKey("");
  }

  function signOut() {
    clearAdminKey();
    setSavedKey(null);
    setStats(null);
    setError(null);
  }

  if (!savedKey) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
        <h1 className="text-2xl font-semibold text-ink-900">Owner dashboard</h1>
        <p className="mt-2 text-sm text-ink-500">
          Enter the admin secret from your server <code className="rounded bg-ink-100 px-1">.env</code>.
          Not linked from the public site.
        </p>
        <form onSubmit={unlock} className="mt-6 space-y-3">
          <input
            type="password"
            autoComplete="off"
            placeholder="Admin secret"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            className="w-full rounded-xl border border-ink-200 px-4 py-3 text-ink-900 outline-none ring-accent/60 focus:ring-2"
          />
          <button
            type="submit"
            className="w-full rounded-xl bg-indigo-600 px-4 py-3 font-medium text-white hover:bg-indigo-700"
          >
            Unlock
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-2xl px-6 py-12">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-ink-900">Demo stats</h1>
        <button
          type="button"
          onClick={signOut}
          className="text-sm text-ink-500 underline hover:text-ink-900"
        >
          Sign out
        </button>
      </div>
      <p className="mt-1 text-sm text-ink-500">
        Refreshes when you reload. LLM counters track calls since last Redis reset.
      </p>

      {loading && <p className="mt-8 text-sm text-ink-400">Loading…</p>}

      {stats && (
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <StatCard label="Videos (ready)" value={stats.videos_ready} />
          <StatCard label="Videos (total)" value={stats.videos_total} />
          <StatCard label="In progress" value={stats.videos_processing} />
          <StatCard label="Failed / rejected" value={stats.videos_failed} />
          <StatCard label="Jobs completed" value={stats.jobs_completed} />
          <StatCard label="Jobs failed" value={stats.jobs_failed} />
          <StatCard label="LLM API calls" value={stats.llm_calls} />
          <StatCard label="LLM tokens (approx)" value={stats.llm_tokens} />
        </div>
      )}

      {stats && stats.recent_videos.length > 0 && (
        <section className="mt-10">
          <h2 className="font-semibold text-ink-900">Ready docs</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {stats.recent_videos.map((v) => (
              <li key={v.id} className="rounded-lg border border-ink-200 px-3 py-2">
                <a href={`/doc/?id=${v.id}`} className="font-medium text-indigo-600 hover:underline">
                  {v.title ?? v.youtube_id}
                </a>
                {v.channel && <span className="text-ink-500"> — {v.channel}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-ink-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-ink-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-ink-900">{value.toLocaleString()}</p>
    </div>
  );
}
