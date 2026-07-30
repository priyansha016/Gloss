import type { VideoDocument } from "./api";

/** Build a Markdown study-notes document from the doc. */
export function buildMarkdown(doc: VideoDocument): string {
  const out: string[] = [];
  const ov = doc.overview;

  out.push(`# ${doc.title ?? "Study notes"}`);
  if (doc.channel) out.push(`_${doc.channel}_`);
  out.push("");

  if (ov?.teaches) out.push("## What you'll learn", "", ov.teaches, "");
  if (ov?.prerequisites?.length) out.push(`**Prerequisites:** ${ov.prerequisites.join(", ")}`, "");
  if (ov?.summary?.length) out.push("## Key takeaways", "", ...ov.summary.map((s) => `- ${s}`), "");
  if (ov?.commands?.length) {
    out.push("## Commands", "");
    ov.commands.forEach((c) => out.push(`- \`${c.cmd}\`${c.purpose ? ` — ${c.purpose}` : ""}`));
    out.push("");
  }

  out.push("## Sections", "");
  doc.sections.forEach((s) => {
    const c = s.content;
    out.push(`### ${s.title}`);
    if (c?.headline) out.push("", c.headline);
    if (c?.explainer) out.push("", c.explainer);
    if (c?.key_points?.length) {
      out.push("");
      c.key_points.forEach((p) => out.push(`- ${p}`));
    }
    out.push("");
  });

  if (ov?.notes?.length) {
    out.push("## Notes", "");
    ov.notes.forEach((n) => {
      out.push(`### ${n.heading}`);
      n.bullets.forEach((b) => out.push(`- ${b}`));
      out.push("");
    });
  }
  if (ov?.qa?.length) {
    out.push("## Q&A", "");
    ov.qa.forEach((q, i) => out.push(`**Q${i + 1} (${q.kind}). ${q.question}**`, "", q.answer, ""));
  }

  return out.join("\n");
}

/** Trigger a client-side download of a text file. */
export function downloadText(filename: string, content: string, type = "text/markdown"): void {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
