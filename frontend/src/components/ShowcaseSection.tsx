"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getShowcase, type ShowcaseVideo } from "@/lib/api";

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function ShowcaseSection() {
  const [items, setItems] = useState<ShowcaseVideo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getShowcase()
      .catch(() =>
        fetch("/showcase.json")
          .then((r) => (r.ok ? r.json() : []))
          .catch(() => [] as ShowcaseVideo[])
      )
      .then((data) => setItems(Array.isArray(data) ? data : []))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <p className="mt-10 text-sm text-ink-400">Loading examples…</p>
    );
  }

  if (items.length === 0) {
    return null;
  }

  return (
    <section className="mt-12">
      <h2 className="text-lg font-semibold text-ink-900">See it in action</h2>
      <p className="mt-1 text-sm text-ink-500">
        Browse study docs already built — no URL needed.
      </p>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2">
        {items.map((v) => (
          <li key={v.id}>
            <Link
              href={`/doc/?id=${v.id}`}
              className="group flex flex-col rounded-2xl border border-ink-200/80 bg-white/80 p-4 shadow-sm backdrop-blur-sm transition hover:border-indigo-300 hover:shadow-md"
            >
              <span className="font-medium text-ink-900 group-hover:text-indigo-700">
                {v.title ?? "Untitled video"}
              </span>
              <span className="mt-1 text-sm text-ink-500">
                {[v.channel, formatDuration(v.duration_s)].filter(Boolean).join(" · ")}
              </span>
              <span className="mt-2 text-sm font-medium text-indigo-600">
                Open study doc →
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
