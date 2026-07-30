import { UrlForm } from "@/components/UrlForm";
import { ShowcaseSection } from "@/components/ShowcaseSection";

const DEMO_OFFLINE = process.env.NEXT_PUBLIC_DEMO_OFFLINE === "true";

const FEATURES = [
  {
    title: "Beginner glossary",
    body: "Every jargon term defined in plain English, linked right where it appears — no more homework to understand the notes.",
    chip: "bg-fuchsia-100 text-fuchsia-700",
    ring: "hover:border-fuchsia-300",
    icon: "✦",
  },
  {
    title: "Diagrams & worked examples",
    body: "Architecture flows, concept maps, step-by-step math and commands — rebuilt from the video so you can actually see it.",
    chip: "bg-sky-100 text-sky-700",
    ring: "hover:border-sky-300",
    icon: "◈",
  },
  {
    title: "Notes, Q&A + Ask",
    body: "Ready-made study notes, interview questions, and a chat that answers from the video itself — with timestamps.",
    chip: "bg-emerald-100 text-emerald-700",
    ring: "hover:border-emerald-300",
    icon: "❋",
  },
];

const STEPS = [
  { n: "1", label: "Paste a YouTube URL" },
  { n: "2", label: "Gloss builds the study doc" },
  { n: "3", label: "Skim, ask, download — done" },
];

export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-white">
      {/* Decorative glow */}
      <div className="pointer-events-none absolute -top-40 left-1/2 h-[480px] w-[720px] -translate-x-1/2 rounded-full bg-gradient-to-br from-indigo-200 via-violet-200 to-fuchsia-200 opacity-60 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-48 -right-32 h-[400px] w-[520px] rounded-full bg-gradient-to-tr from-sky-200 via-teal-100 to-emerald-100 opacity-50 blur-3xl" />
      <div className="pointer-events-none absolute -left-40 top-1/3 h-[320px] w-[420px] rounded-full bg-gradient-to-br from-pink-100 via-fuchsia-100 to-amber-50 opacity-50 blur-3xl" />

      <div className="relative mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-16">
        <div className="mb-10 space-y-5">
          <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-1.5 text-sm font-semibold tracking-wide text-white shadow-md shadow-indigo-200">
            ✦ Gloss
          </span>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-ink-900 sm:text-6xl">
            Learnable video notes,{" "}
            <span className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 bg-clip-text text-transparent">
              not just summaries
            </span>
          </h1>
          <p className="max-w-2xl text-lg leading-relaxed text-ink-500">
            Paste a YouTube lecture or tutorial. Get connected study notes with plain-English
            explainers, a beginner glossary, diagrams, and clickable timestamps into the video.
          </p>
        </div>

        {DEMO_OFFLINE ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-amber-950">
            <p className="font-semibold">Live demo is paused</p>
            <p className="mt-1 text-sm leading-relaxed text-amber-900/90">
              Run Gloss on your machine — clone the repo, set a free Groq (or Gemini) key in{" "}
              <code className="rounded bg-amber-100 px-1">.env</code>, and follow the README.
              Bring-your-own-key is built in for when a public backend is online again.
            </p>
            <a
              href="https://github.com/priyansha016/Gloss"
              className="mt-3 inline-block text-sm font-medium text-indigo-700 underline hover:text-indigo-900"
            >
              github.com/priyansha016/Gloss →
            </a>
          </div>
        ) : (
          <UrlForm />
        )}

        {!DEMO_OFFLINE && <ShowcaseSection />}

        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2">
          {STEPS.map((s) => (
            <span key={s.n} className="flex items-center gap-2 text-sm text-ink-500">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-[11px] font-semibold text-white">
                {s.n}
              </span>
              {s.label}
            </span>
          ))}
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className={`rounded-2xl border border-ink-200/80 bg-white/80 p-5 shadow-sm backdrop-blur-sm transition ${f.ring} hover:shadow-md`}
            >
              <span
                className={`mb-3 inline-flex h-8 w-8 items-center justify-center rounded-lg text-base ${f.chip}`}
              >
                {f.icon}
              </span>
              <h2 className="mb-1.5 font-semibold text-ink-900">{f.title}</h2>
              <p className="text-sm leading-relaxed text-ink-500">{f.body}</p>
            </div>
          ))}
        </div>

        <p className="mt-8 text-sm text-ink-400">
          <span className="mr-1 text-emerald-500">●</span>
          Already-glossed videos load instantly from cache. Works with tutorials, lectures &
          courses — not music videos or Q&amp;A compilations.
        </p>
      </div>
    </main>
  );
}
