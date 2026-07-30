"use client";

import { useEffect, useRef, useState } from "react";

let initialized = false;

/** Render Mermaid source to SVG client-side. Renders nothing if the source is invalid. */
export function MermaidDiagram({ source }: { source: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!source) return;
    let cancelled = false;

    (async () => {
      try {
        // Dynamic import: mermaid touches browser APIs, keep it out of SSR.
        const mermaid = (await import("mermaid")).default;
        if (!initialized) {
          mermaid.initialize({
            startOnLoad: false,
            theme: "neutral",
            securityLevel: "strict",
            // Without this, mermaid 11 injects a "Syntax error" bomb SVG into the
            // page on invalid input even when render() throws.
            suppressErrorRendering: true,
          });
          initialized = true;
        }
        // Validate first: parse() throws on bad syntax without touching the DOM.
        await mermaid.parse(source);
        const id = `m${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(id, source);
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [source]);

  if (!source || failed) return null;

  return (
    <div
      ref={ref}
      className="my-3 flex justify-center overflow-x-auto rounded-xl border border-ink-200 bg-white p-4"
    />
  );
}
