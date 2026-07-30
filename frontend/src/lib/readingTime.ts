import type { VideoDocument } from "./api";

/** Rough read time (min) for the generated doc, at ~200 wpm. */
export function estimateReadMinutes(doc: VideoDocument): number {
  let words = 0;
  const count = (s?: string | null) => {
    if (s) words += s.split(/\s+/).filter(Boolean).length;
  };
  const ov = doc.overview;
  if (ov) {
    count(ov.teaches);
    ov.summary?.forEach(count);
    ov.notes?.forEach((n) => n.bullets.forEach(count));
    ov.qa?.forEach((q) => {
      count(q.question);
      count(q.answer);
    });
  }
  doc.sections.forEach((s) => {
    const c = s.content;
    if (!c) return;
    count(c.headline);
    count(c.explainer);
    c.key_points.forEach(count);
    c.walkthrough.forEach((w) => count(w.text));
  });
  return Math.max(1, Math.round(words / 200));
}
