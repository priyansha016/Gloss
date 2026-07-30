"use client";

import { useState } from "react";
import { generatePractice, isUserKeyRequired, type Flashcard, type QuizQuestion } from "@/lib/api";
import { ApiKeyModal } from "./ApiKeyModal";

export function PracticeTab({
  videoId,
  initialCards,
  initialQuiz,
}: {
  videoId: string;
  initialCards?: Flashcard[];
  initialQuiz?: QuizQuestion[];
}) {
  const [cards, setCards] = useState<Flashcard[] | null>(initialCards?.length ? initialCards : null);
  const [quiz, setQuiz] = useState<QuizQuestion[] | null>(initialQuiz?.length ? initialQuiz : null);
  const [busy, setBusy] = useState<"flashcards" | "quiz" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsKey, setNeedsKey] = useState(false);

  const generate = async (kind: "flashcards" | "quiz") => {
    setBusy(kind);
    setError(null);
    try {
      const res = await generatePractice(videoId, kind);
      if (kind === "flashcards") setCards(res.cards);
      else setQuiz(res.questions);
    } catch (err) {
      if (isUserKeyRequired(err)) {
        setNeedsKey(true);
        return; // the finally block still clears `busy`
      }
      let msg = "Generation failed — please try again.";
      if (err instanceof Error) {
        try {
          const detail = JSON.parse(err.message)?.detail;
          if (typeof detail === "string" && detail) msg = detail;
        } catch {
          /* keep generic */
        }
      }
      setError(msg);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-ink-500">
        Practice tools are generated on demand from this video&rsquo;s notes, then saved — the
        first generation takes a few seconds.
      </p>
      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <ApiKeyModal
        open={needsKey}
        reason="Generating practice material runs on your own AI provider key."
        onClose={() => setNeedsKey(false)}
      />

      {cards ? (
        <FlashcardDeck cards={cards} />
      ) : (
        <GenerateCard
          title="Flashcards"
          body="Flip-style cards for the video's key terms and concepts — great for quick review."
          cta="Generate flashcards"
          busy={busy === "flashcards"}
          onClick={() => generate("flashcards")}
        />
      )}

      {quiz ? (
        <QuizRunner questions={quiz} />
      ) : (
        <GenerateCard
          title="Quiz"
          body="Multiple-choice questions with instant feedback to check you actually got it."
          cta="Generate quiz"
          busy={busy === "quiz"}
          onClick={() => generate("quiz")}
        />
      )}
    </div>
  );
}

function GenerateCard({
  title,
  body,
  cta,
  busy,
  onClick,
}: {
  title: string;
  body: string;
  cta: string;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <div className="rounded-2xl border border-rose-200 bg-gradient-to-br from-rose-50/70 to-pink-50/40 p-6">
      <h3 className="mb-1 font-semibold text-ink-900">{title}</h3>
      <p className="mb-4 text-sm leading-relaxed text-ink-500">{body}</p>
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        className="rounded-xl bg-gradient-to-r from-rose-500 to-pink-600 px-5 py-2.5 text-sm font-medium text-white shadow-md shadow-rose-200 transition hover:from-rose-600 hover:to-pink-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? (
          <span className="flex items-center gap-2">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            Generating…
          </span>
        ) : (
          `✨ ${cta}`
        )}
      </button>
    </div>
  );
}

function FlashcardDeck({ cards }: { cards: Flashcard[] }) {
  const [idx, setIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const card = cards[idx];

  const go = (delta: number) => {
    setFlipped(false);
    setIdx((i) => (i + delta + cards.length) % cards.length);
  };

  return (
    <div className="rounded-2xl border border-rose-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-ink-900">Flashcards</h3>
        <span className="text-sm text-ink-400">
          {idx + 1} / {cards.length}
        </span>
      </div>

      <button
        type="button"
        onClick={() => setFlipped((v) => !v)}
        className={`flex min-h-[180px] w-full items-center justify-center rounded-2xl border-2 p-6 text-center transition ${
          flipped
            ? "border-rose-300 bg-gradient-to-br from-rose-50 to-pink-50"
            : "border-ink-200 bg-ink-50 hover:border-rose-300"
        }`}
      >
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-400">
            {flipped ? "Answer" : "Question — click to flip"}
          </p>
          <p className={`leading-relaxed ${flipped ? "text-ink-700" : "text-lg font-medium text-ink-900"}`}>
            {flipped ? card.back : card.front}
          </p>
        </div>
      </button>

      <div className="mt-3 flex items-center justify-between">
        <button
          type="button"
          onClick={() => go(-1)}
          className="rounded-lg px-4 py-2 text-sm font-medium text-ink-600 transition hover:bg-ink-50"
        >
          ← Previous
        </button>
        <button
          type="button"
          onClick={() => go(1)}
          className="rounded-lg bg-gradient-to-r from-rose-500 to-pink-600 px-4 py-2 text-sm font-medium text-white transition hover:from-rose-600 hover:to-pink-700"
        >
          Next →
        </button>
      </div>
    </div>
  );
}

function QuizRunner({ questions }: { questions: QuizQuestion[] }) {
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [score, setScore] = useState(0);
  const [done, setDone] = useState(false);
  const q = questions[idx];

  const pick = (i: number) => {
    if (picked !== null) return;
    setPicked(i);
    if (i === q.answer) setScore((s) => s + 1);
  };

  const next = () => {
    if (idx + 1 >= questions.length) {
      setDone(true);
    } else {
      setIdx((i) => i + 1);
      setPicked(null);
    }
  };

  const restart = () => {
    setIdx(0);
    setPicked(null);
    setScore(0);
    setDone(false);
  };

  if (done) {
    const pct = Math.round((score / questions.length) * 100);
    return (
      <div className="rounded-2xl border border-rose-200 bg-white p-8 text-center">
        <p className="text-4xl font-semibold text-ink-900">
          {score}/{questions.length}
        </p>
        <p className="mb-4 mt-1 text-ink-500">
          {pct >= 80 ? "Excellent — you got it. 🎉" : pct >= 50 ? "Solid — review the misses and retry." : "Worth another pass through the doc, then retry."}
        </p>
        <button
          type="button"
          onClick={restart}
          className="rounded-xl bg-gradient-to-r from-rose-500 to-pink-600 px-5 py-2.5 text-sm font-medium text-white transition hover:from-rose-600 hover:to-pink-700"
        >
          Retry quiz
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-rose-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-ink-900">Quiz</h3>
        <span className="text-sm text-ink-400">
          {idx + 1} / {questions.length} · score {score}
        </span>
      </div>

      <p className="mb-4 font-medium leading-relaxed text-ink-900">{q.question}</p>
      <div className="space-y-2">
        {q.options.map((opt, i) => {
          let cls = "border-ink-200 bg-white hover:border-rose-300 text-ink-700";
          if (picked !== null) {
            if (i === q.answer) cls = "border-emerald-400 bg-emerald-50 text-emerald-900";
            else if (i === picked) cls = "border-red-300 bg-red-50 text-red-800";
            else cls = "border-ink-100 bg-white text-ink-400";
          }
          return (
            <button
              key={i}
              type="button"
              onClick={() => pick(i)}
              disabled={picked !== null}
              className={`block w-full rounded-xl border px-4 py-3 text-left text-sm leading-relaxed transition ${cls}`}
            >
              <span className="mr-2 font-semibold">{String.fromCharCode(65 + i)}.</span>
              {opt}
            </button>
          );
        })}
      </div>

      {picked !== null && (
        <div className="mt-4 space-y-3">
          {q.explanation && (
            <p className="rounded-xl bg-ink-50 px-4 py-3 text-sm leading-relaxed text-ink-600">
              {picked === q.answer ? "✓ Correct. " : "✗ Not quite. "}
              {q.explanation}
            </p>
          )}
          <button
            type="button"
            onClick={next}
            className="rounded-xl bg-gradient-to-r from-rose-500 to-pink-600 px-5 py-2.5 text-sm font-medium text-white transition hover:from-rose-600 hover:to-pink-700"
          >
            {idx + 1 >= questions.length ? "See score" : "Next question →"}
          </button>
        </div>
      )}
    </div>
  );
}
