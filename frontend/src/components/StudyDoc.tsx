"use client";

import { useMemo, useState } from "react";
import type {
  DocOverview,
  GlossaryTerm,
  Section,
  SectionContent,
  TranscriptSegment,
  VideoDocument,
  WalkStep,
} from "@/lib/api";
import { getSectionTerms, pickDefaultTerm } from "@/lib/glossaryContext";
import { highlightGlossaryTerms } from "@/lib/glossaryHighlight";
import { formatDuration, formatTimestamp } from "@/lib/format";
import { estimateReadMinutes } from "@/lib/readingTime";
import { buildMarkdown, downloadText } from "@/lib/download";
import { ChatPanel } from "./ChatPanel";
import { CommandsBlock } from "./CommandsBlock";
import { GlossaryPanel } from "./GlossaryPanel";
import { MathBlock } from "./MathBlock";
import { MermaidDiagram } from "./MermaidDiagram";
import { NotesView } from "./NotesView";
import { PracticeTab } from "./PracticeTab";
import { QAView } from "./QAView";
import { YouTubePlayer } from "./YouTubePlayer";

type StudyDocProps = { doc: VideoDocument };
type SelectTerm = (id: string | null) => void;
type Tab = "doc" | "notes" | "qa" | "practice";

export function StudyDoc({ doc }: StudyDocProps) {
  // {t, n}: n increments per click so repeated jumps (even to the same time) always seek
  const [seek, setSeek] = useState({ t: 0, n: 0 });
  const setSeekTo = (t: number) => setSeek((s) => ({ t, n: s.n + 1 }));
  const [showRaw, setShowRaw] = useState(false);
  const [tab, setTab] = useState<Tab>("doc");
  const [askOpen, setAskOpen] = useState(false);
  const firstSection = doc.sections[0] ?? null;
  const [focusedSectionId, setFocusedSectionId] = useState<string | null>(firstSection?.id ?? null);
  const [showAllGlossaryTerms, setShowAllGlossaryTerms] = useState(false);
  const [activeTermId, setActiveTermId] = useState<string | null>(() =>
    firstSection ? pickDefaultTerm(getSectionTerms(firstSection, doc)) : null,
  );

  const overview = doc.overview;
  const glossaryTerms = doc.glossary;
  const focusedSection = doc.sections.find((s) => s.id === focusedSectionId) ?? null;
  const panelTerms = useMemo(() => {
    if (showAllGlossaryTerms || !focusedSection) return glossaryTerms;
    return getSectionTerms(focusedSection, doc);
  }, [doc, focusedSection, glossaryTerms, showAllGlossaryTerms]);

  const readMin = estimateReadMinutes(doc);
  const videoMin = doc.duration_s ? Math.round(doc.duration_s / 60) : null;

  // Video-specific chat starters, derived from this doc's own glossary + sections.
  const askSuggestions = useMemo(() => {
    const out: string[] = [];
    if (doc.glossary[0]) out.push(`What is ${doc.glossary[0].display}, in simple terms?`);
    const mid = doc.sections[Math.floor(doc.sections.length / 2)];
    if (mid) out.push(`Explain "${mid.title}" like I'm new to this`);
    out.push(
      overview?.commands?.length
        ? "Where does the hands-on demo start?"
        : "How do the main ideas connect?",
    );
    return out;
  }, [doc, overview]);
  const notesCount = overview?.notes?.length ?? 0;
  const qaCount = overview?.qa?.length ?? 0;

  const focusSection = (section: Section, termId?: string | null) => {
    setFocusedSectionId(section.id);
    if (termId !== undefined) {
      setActiveTermId(termId);
      return;
    }
    setActiveTermId((current) => {
      const sectionTerms = getSectionTerms(section, doc);
      if (current && sectionTerms.some((t) => t.id === current)) return current;
      return pickDefaultTerm(sectionTerms);
    });
  };

  const handleSelectTerm = (termId: string | null) => {
    setActiveTermId(termId);
    if (termId && focusedSectionId) {
      const stillRelevant = getSectionTerms(
        doc.sections.find((s) => s.id === focusedSectionId)!,
        doc,
      ).some((t) => t.id === termId);
      if (!stillRelevant) setShowAllGlossaryTerms(true);
    }
  };

  const handleDownload = () => {
    const slug = (doc.title ?? doc.youtube_id).replace(/[^a-z0-9]+/gi, "-").slice(0, 60);
    downloadText(`${slug || "gloss-notes"}.md`, buildMarkdown(doc));
  };

  const jumpToSection = (section: Section) => {
    setTab("doc");
    setSeekTo(section.start_s);
    focusSection(section);
    document.getElementById(`sec-${section.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // First moment each glossary term is spoken (earliest stored occurrence).
  const firstUse = useMemo(() => {
    const map = new Map<string, { t: number; sectionId: string | null }>();
    for (const occ of doc.term_occurrences) {
      if (occ.segment_idx == null) continue;
      const seg = doc.cleaned_segments[occ.segment_idx];
      if (!seg) continue;
      const cur = map.get(occ.term_id);
      if (!cur || seg.start_s < cur.t) {
        map.set(occ.term_id, { t: seg.start_s, sectionId: occ.section_id });
      }
    }
    return map;
  }, [doc]);

  const jumpToFirstUse = (termId: string) => {
    const hit = firstUse.get(termId);
    if (!hit) return;
    setTab("doc");
    setSeekTo(hit.t);
    const section = doc.sections.find((s) => s.id === hit.sectionId);
    if (section) {
      focusSection(section, termId);
      document.getElementById(`sec-${section.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div className="mx-auto grid max-w-[1500px] gap-8 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[230px_minmax(0,1fr)_380px]">
      {/* Left rail: section navigation + Ask (wide screens) */}
      <div className="hidden xl:block">
        <div className="sticky top-6 space-y-4">
          <nav className="rounded-2xl border border-ink-200 bg-white p-3">
            <h3 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
              Sections
            </h3>
            <ul className="max-h-[36vh] space-y-0.5 overflow-y-auto">
              {doc.sections.map((section) => (
                <li key={section.id}>
                  <button
                    type="button"
                    onClick={() => jumpToSection(section)}
                    className={`w-full rounded-lg px-2 py-1.5 text-left text-sm transition ${
                      section.id === focusedSectionId
                        ? "bg-accent-soft font-medium text-accent"
                        : "text-ink-700 hover:bg-ink-50"
                    }`}
                  >
                    <span className="mr-1.5 font-mono text-[11px] text-ink-400">
                      {formatTimestamp(section.start_s)}
                    </span>
                    {section.title.length > 26 ? `${section.title.slice(0, 26)}…` : section.title}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </div>

      <div className="min-w-0 space-y-6">
        <header className="space-y-2">
          <p className="w-fit bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-sm font-semibold uppercase tracking-wide text-transparent">
            ✦ Gloss
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-ink-900">
            {doc.title ?? "Untitled video"}
          </h1>
          <div className="flex flex-wrap items-center gap-3 text-sm text-ink-500">
            {doc.channel && <span>{doc.channel}</span>}
            {doc.duration_s != null && <span>{formatDuration(doc.duration_s)}</span>}
            {doc.lang && <span>Captions: {doc.lang}</span>}
            <span className="rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-0.5 text-xs font-medium text-white shadow-sm">
              ≈{readMin} min read
              {videoMin != null && videoMin > readMin ? ` · saves ~${videoMin - readMin} min` : ""}
            </span>
          </div>
        </header>

        <Tabs tab={tab} setTab={setTab} notesCount={notesCount} qaCount={qaCount} />

        {tab === "doc" && (
          <div className="space-y-8">
            <OverviewSection
              overview={overview}
              tldr={doc.tldr}
              glossaryTerms={glossaryTerms}
              activeTermId={activeTermId}
              onSelectTerm={handleSelectTerm}
              onJump={setSeekTo}
            />

            <section className="space-y-4">
              <h2 className="text-lg font-semibold text-ink-900">Sections</h2>
              <p className="text-sm text-ink-500">
                Each section has a plain-English explainer, key points, and a diagram where it helps.
                Click a timestamp to jump in the video.
              </p>
              <div className="space-y-4">
                {doc.sections.map((section) => (
                  <SectionCard
                    key={section.id}
                    section={section}
                    cleanedSegments={segmentsForSection(doc.cleaned_segments, section)}
                    sectionTerms={getSectionTerms(section, doc)}
                    activeTermId={activeTermId}
                    isFocused={section.id === focusedSectionId}
                    onFocusSection={focusSection}
                    onSelectTerm={handleSelectTerm}
                    onJump={setSeekTo}
                  />
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-ink-200 bg-white">
              <button
                type="button"
                onClick={() => setShowRaw((v) => !v)}
                className="flex w-full items-center justify-between px-5 py-4 text-left font-medium text-ink-900"
              >
                Raw transcript (original captions — timestamps let you jump to that moment)
                <span className="text-sm text-ink-500">{showRaw ? "Hide" : "Show"}</span>
              </button>
              {showRaw && (
                <div className="max-h-96 overflow-y-auto border-t border-ink-100 px-5 py-4">
                  <TranscriptView segments={doc.raw_segments} onJump={setSeekTo} />
                </div>
              )}
            </section>
          </div>
        )}

        {tab === "notes" && <NotesView notes={overview?.notes ?? []} />}
        {tab === "qa" && <QAView qa={overview?.qa ?? []} />}
        {tab === "practice" && (
          <PracticeTab
            videoId={doc.id}
            initialCards={overview?.flashcards}
            initialQuiz={overview?.quiz}
          />
        )}
      </div>

      <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <YouTubePlayer
          youtubeId={doc.youtube_id}
          startSeconds={seek.t}
          seekNonce={seek.n}
          title={doc.title ?? undefined}
        />
        <button
          type="button"
          onClick={handleDownload}
          className="w-full rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-sm font-medium text-ink-700 shadow-sm transition hover:bg-ink-50"
        >
          ↓ Download notes (.md)
        </button>
        <GlossaryPanel
          terms={panelTerms}
          activeTermId={activeTermId}
          onSelect={handleSelectTerm}
          focusedSection={focusedSection}
          showAllTerms={showAllGlossaryTerms}
          onToggleShowAll={() => setShowAllGlossaryTerms((v) => !v)}
          firstUseTimeFor={(id) => firstUse.get(id)?.t ?? null}
          onJumpToFirstUse={jumpToFirstUse}
        />
        <nav className="rounded-2xl border border-ink-200 bg-white p-4 xl:hidden">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-500">
            Jump to section
          </h3>
          <ul className="space-y-2">
            {doc.sections.map((section) => (
              <li key={section.id}>
                <button
                  type="button"
                  onClick={() => jumpToSection(section)}
                  className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm transition hover:bg-ink-50"
                >
                  <span className="shrink-0 font-mono text-xs text-accent">
                    {formatTimestamp(section.start_s)}
                  </span>
                  <span className="text-ink-700">{section.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      {/* Floating Ask dock: stays mounted so chat history survives open/close */}
      <div className="fixed bottom-6 right-6 z-50">
        <div
          className={`${askOpen ? "flex" : "hidden"} h-[min(600px,calc(100vh-6rem))] w-[min(430px,calc(100vw-3rem))] flex-col shadow-2xl shadow-teal-900/20`}
        >
          <div className="relative h-full">
            <button
              type="button"
              onClick={() => setAskOpen(false)}
              className="absolute right-3 top-2.5 z-10 rounded-full px-2 py-0.5 text-lg leading-none text-white/80 transition hover:bg-white/20 hover:text-white"
              aria-label="Close Ask"
            >
              ×
            </button>
            <ChatPanel videoId={doc.id} onJump={setSeekTo} suggestions={askSuggestions} />
          </div>
        </div>
        {!askOpen && (
          <button
            type="button"
            onClick={() => setAskOpen(true)}
            className="flex items-center gap-2 rounded-full bg-gradient-to-r from-teal-500 to-cyan-600 px-5 py-3 font-medium text-white shadow-lg shadow-teal-500/30 transition hover:scale-105 hover:from-teal-600 hover:to-cyan-700"
          >
            ✦ Ask this video
          </button>
        )}
      </div>
    </div>
  );
}

function Tabs({
  tab,
  setTab,
  notesCount,
  qaCount,
}: {
  tab: Tab;
  setTab: (t: Tab) => void;
  notesCount: number;
  qaCount: number;
}) {
  const items: { id: Tab; label: string; count?: number; active: string; idle: string }[] = [
    {
      id: "doc",
      label: "Study doc",
      active: "bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-200",
      idle: "text-ink-500 hover:bg-indigo-50 hover:text-indigo-700",
    },
    {
      id: "notes",
      label: "Notes",
      count: notesCount,
      active: "bg-gradient-to-r from-emerald-500 to-teal-600 text-white shadow-md shadow-emerald-200",
      idle: "text-ink-500 hover:bg-emerald-50 hover:text-emerald-700",
    },
    {
      id: "qa",
      label: "Q&A",
      count: qaCount,
      active: "bg-gradient-to-r from-amber-500 to-orange-500 text-white shadow-md shadow-amber-200",
      idle: "text-ink-500 hover:bg-amber-50 hover:text-amber-700",
    },
    {
      id: "practice",
      label: "✨ Practice",
      active: "bg-gradient-to-r from-rose-500 to-pink-600 text-white shadow-md shadow-rose-200",
      idle: "text-ink-500 hover:bg-rose-50 hover:text-rose-700",
    },
  ];
  return (
    <div className="flex flex-wrap gap-1.5 rounded-2xl border border-ink-200 bg-white p-1.5 shadow-sm">
      {items.map((it) => (
        <button
          key={it.id}
          type="button"
          onClick={() => setTab(it.id)}
          className={`rounded-xl px-4 py-2 text-sm font-medium transition ${
            tab === it.id ? it.active : it.idle
          }`}
        >
          {it.label}
          {it.count ? (
            <span className={`ml-1.5 text-xs ${tab === it.id ? "text-white/70" : "text-ink-400"}`}>
              {it.count}
            </span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

function OverviewSection({
  overview,
  tldr,
  glossaryTerms,
  activeTermId,
  onSelectTerm,
  onJump,
}: {
  overview: DocOverview | null;
  tldr: string | null;
  glossaryTerms: GlossaryTerm[];
  activeTermId: string | null;
  onSelectTerm: SelectTerm;
  onJump: (seconds: number) => void;
}) {
  if (!overview && !tldr) return null;
  const seen = new Set<string>();
  const hl = (text: string) => highlightGlossaryTerms(text, glossaryTerms, activeTermId, onSelectTerm, seen);

  return (
    <section className="space-y-5 rounded-2xl border border-indigo-200/70 bg-gradient-to-br from-indigo-50 via-white to-violet-50 p-6 shadow-sm">
      {overview?.teaches && (
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-accent">
            What you&rsquo;ll learn
          </h2>
          <p className="leading-relaxed text-ink-700">{hl(overview.teaches)}</p>
        </div>
      )}

      {overview && overview.summary.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-sky-600">
            Key takeaways
          </h3>
          <ul className="space-y-1.5">
            {overview.summary.map((s, i) => (
              <li key={i} className="flex gap-2 leading-relaxed text-ink-700">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gradient-to-br from-sky-400 to-indigo-500" />
                <span>{hl(s)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {overview && overview.prerequisites.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-600">
            Assumes you know
          </h3>
          <div className="flex flex-wrap gap-2">
            {overview.prerequisites.map((p, i) => (
              <span
                key={i}
                className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm text-amber-800"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      )}

      {overview?.concept_map && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-violet-600">
            How it fits together
          </h3>
          <MermaidDiagram source={overview.concept_map} />
        </div>
      )}

      {overview && overview.commands.length > 0 && <CommandsBlock commands={overview.commands} />}

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
          Skim by section
        </h3>
        {overview && overview.nav.length > 0 ? (
          <div className="space-y-1.5">
            {overview.nav.map((item, i) => (
              <p key={i} className="leading-relaxed text-ink-700">
                <button
                  type="button"
                  onClick={() => onJump(item.t)}
                  className="mr-1 font-mono text-xs font-medium text-sky-600 hover:underline"
                >
                  [{formatTimestamp(item.t)}]
                </button>
                <span className="font-medium text-ink-900">{item.label}:</span> {hl(item.one_liner)}
              </p>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function segmentsForSection(segments: TranscriptSegment[], section: Section) {
  return segments.filter((s) => s.start_s >= section.start_s && s.start_s < section.end_s);
}

function SectionCard({
  section,
  cleanedSegments,
  sectionTerms,
  activeTermId,
  isFocused,
  onFocusSection,
  onSelectTerm,
  onJump,
}: {
  section: Section;
  cleanedSegments: TranscriptSegment[];
  sectionTerms: GlossaryTerm[];
  activeTermId: string | null;
  isFocused: boolean;
  onFocusSection: (section: Section, termId?: string | null) => void;
  onSelectTerm: SelectTerm;
  onJump: (seconds: number) => void;
}) {
  const [showDetail, setShowDetail] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [showExplainer, setShowExplainer] = useState(false);

  const content = section.content;
  const headline = content?.headline || section.summary_short || "";
  const explainer = content?.explainer ?? "";
  const keyPoints = content?.key_points ?? [];
  const walkthrough = content?.walkthrough ?? [];
  const diagram = content?.diagram ?? "";

  // Dedupe glossary highlights within this section: each term highlights once,
  // in DOM order (headline → explainer → key points → walkthrough → transcript).
  const seen = new Set<string>();
  const highlight = (text: string) =>
    highlightGlossaryTerms(
      text,
      sectionTerms,
      activeTermId,
      (id) => {
        onFocusSection(section, id);
        onSelectTerm(id);
      },
      seen,
    );

  return (
    <article
      id={`sec-${section.id}`}
      className={`scroll-mt-24 rounded-2xl border bg-white p-5 shadow-sm transition hover:shadow-md ${
        isFocused ? "border-accent ring-1 ring-accent/30" : "border-ink-200"
      }`}
      onMouseEnter={() => onFocusSection(section)}
    >
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => onJump(section.start_s)}
          className="rounded-full bg-sky-100 px-3 py-1 font-mono text-xs font-medium text-sky-700 transition hover:bg-sky-200"
        >
          {formatTimestamp(section.start_s)}
        </button>
        <h3 className="text-lg font-semibold text-ink-900">{section.title}</h3>
      </div>

      {sectionTerms.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {sectionTerms.slice(0, 6).map((term) => (
            <button
              key={term.id}
              type="button"
              onClick={() => {
                onFocusSection(section, term.id);
                onSelectTerm(term.id);
              }}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
                activeTermId === term.id
                  ? "bg-accent text-white"
                  : "bg-ink-100 text-ink-700 hover:bg-accent-soft hover:text-accent"
              }`}
            >
              {term.display}
            </button>
          ))}
        </div>
      )}

      {headline && <p className="mb-3 font-medium text-ink-800">{highlight(headline)}</p>}

      {explainer && (
        <div className="mb-3 overflow-hidden rounded-xl border-l-4 border-violet-400 bg-gradient-to-r from-violet-50 to-indigo-50/40">
          <button
            type="button"
            onClick={() => setShowExplainer((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-2.5 text-left"
          >
            <span className="text-xs font-semibold uppercase tracking-wide text-violet-600">
              In plain terms
            </span>
            <span className="text-xs text-violet-400">{showExplainer ? "▲ hide" : "▼ show"}</span>
          </button>
          {showExplainer && (
            <p className="px-4 pb-3 leading-relaxed text-ink-700">{highlight(explainer)}</p>
          )}
        </div>
      )}

      {keyPoints.length > 0 ? (
        <ul className="space-y-1.5">
          {keyPoints.map((point, i) => (
            <li key={i} className="flex gap-2 leading-relaxed text-ink-700">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent/50" />
              <span>{highlight(point)}</span>
            </li>
          ))}
        </ul>
      ) : (
        section.summary_full && (
          <p className="leading-relaxed text-ink-700">{highlight(section.summary_full)}</p>
        )
      )}

      {diagram && (
        <div className="mt-3">
          <MermaidDiagram source={diagram} />
        </div>
      )}

      {content?.visual && content.visual.steps.length > 0 && (
        <VisualWalkthrough visual={content.visual} highlight={highlight} />
      )}

      {walkthrough.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => {
              onFocusSection(section);
              setShowDetail((v) => !v);
            }}
            className="text-sm font-medium text-emerald-600 hover:underline"
          >
            {showDetail ? "Hide worked example" : "Show worked example"}
          </button>
          {showDetail && (
            <div className="mt-3">
              <WalkthroughView steps={walkthrough} highlight={highlight} />
            </div>
          )}
        </div>
      )}

      {cleanedSegments.length > 0 && (
        <div className="mt-3 border-t border-ink-100 pt-3">
          <button
            type="button"
            onClick={() => {
              onFocusSection(section);
              setShowTranscript((v) => !v);
            }}
            className="text-sm font-medium text-ink-500 hover:text-ink-700"
          >
            {showTranscript ? "Hide section transcript" : "Show section transcript"}
          </button>
          {showTranscript && (
            <div className="mt-2 max-h-48 overflow-y-auto text-sm leading-relaxed text-ink-600">
              {cleanedSegments.map((seg, i) => (
                <p key={`${seg.start_s}-${i}`} className="mb-1">
                  <button
                    type="button"
                    onClick={() => onJump(seg.start_s)}
                    className="mr-2 font-mono text-xs text-accent hover:underline"
                  >
                    [{formatTimestamp(seg.start_s)}]
                  </button>
                  {highlight(seg.text)}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function VisualWalkthrough({
  visual,
  highlight,
}: {
  visual: NonNullable<SectionContent["visual"]>;
  highlight: (text: string) => React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-sky-200 bg-gradient-to-br from-sky-50/70 to-indigo-50/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="text-sm font-bold uppercase tracking-wide text-sky-800">
          ◉ Visualize it{visual.focus ? `: ${visual.focus}` : ""}
        </span>
        <span className="text-xs font-medium text-sky-500">{open ? "▲ hide" : "▼ show"}</span>
      </button>
      {open && (
        <ol className="space-y-4 px-4 pb-4">
          {visual.steps.map((step, i) => (
            <li key={i} className="flex gap-3">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-sky-200 text-xs font-semibold text-sky-800">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1 space-y-2">
                <p className="leading-relaxed text-ink-700">{highlight(step.caption)}</p>
                {step.math && <MathBlock tex={step.math} />}
                {step.diagram && <MermaidDiagram source={step.diagram} />}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function WalkthroughView({
  steps,
  highlight,
}: {
  steps: WalkStep[];
  highlight: (text: string) => React.ReactNode;
}) {
  return (
    <ol className="space-y-3">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-xs font-medium text-emerald-700">
            {i + 1}
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            {step.text && <p className="leading-relaxed text-ink-700">{highlight(step.text)}</p>}
            {step.math && <MathBlock tex={step.math} />}
            {step.code && (
              <pre className="overflow-x-auto rounded-lg bg-ink-900 px-3 py-2 text-xs leading-relaxed text-ink-50">
                <code>{step.code}</code>
              </pre>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function TranscriptView({
  segments,
  onJump,
}: {
  segments: TranscriptSegment[];
  onJump: (seconds: number) => void;
}) {
  return (
    <div className="space-y-2 text-sm leading-relaxed text-ink-700">
      {segments.map((seg, i) => (
        <p key={`${seg.start_s}-${i}`}>
          <button
            type="button"
            onClick={() => onJump(seg.start_s)}
            className="mr-2 font-mono text-xs text-accent hover:underline"
          >
            [{formatTimestamp(seg.start_s)}]
          </button>
          {seg.text}
        </p>
      ))}
    </div>
  );
}
