"use client";

import katex from "katex";

/** Render a LaTeX string as a display-mode math block. Falls back to raw text on error. */
export function MathBlock({ tex }: { tex: string }) {
  if (!tex) return null;
  try {
    const html = katex.renderToString(tex, { displayMode: true, throwOnError: false });
    return (
      <span
        className="block overflow-x-auto py-1 text-ink-900"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return <code className="text-ink-700">{tex}</code>;
  }
}
