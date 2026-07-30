# Gloss — YouTube → Interactive Study Doc (Project Plan)

> Product name: **Gloss**. Repo folder may still read `Youtube_skim` from early scaffolding.

> Hand-off brief for Claude Code. Read this whole file before scaffolding. The
> "why" sections are load-bearing — several obvious-looking "improvements"
> (download the video, Whisper everything, one big summary) are explicitly
> rejected below for reasons that aren't obvious from the code.

---

## 1. What we're building

A web tool that takes a YouTube URL (lectures / tutorials / informative videos)
and produces a **structured, interactive study document**: tiered notes,
clickable timestamp jumps into the video, an auto-generated **beginner-friendly
glossary side panel** for technical jargon, and a Q&A box over the content.

Public-hosted, real usage (not just a portfolio piece). The builder will be a
primary user.

## 2. The core bet (do not lose this)

The summarizer space is saturated and commoditized (NoteGPT, Eightify, Sider,
Summarize.tech, etc., all transcript-in / bullets-out). We do **not** win on
summary quality.

We win on **teaching, not compression**. The single differentiator:

> **Auto-detected, inline, beginner-level glossary.** When a CNN video says
> "kernel", "ReLU", "feature map", a beginner doesn't know those words — so a
> normal summary just creates more homework. We detect the jargon automatically
> and surface a plain-English definition in a side panel, linked from each
> occurrence in the doc.

NotebookLM (the strongest competitor) explains *using* jargon the learner
doesn't know. That's the exact gap we attack. **The glossary is the product.**
Everything else is table stakes.

Second-order differentiator: a deliberately **designed learning document**
(tiered depth + timestamp jumps + glossary margin), not a generic chat box.

## 3. Non-negotiable constraints — the "safe zone"

These are product/legal decisions, not preferences. Do not relax them.

1. **Captions only. Never download the video or audio.**
   - Use the existing caption track (e.g. `youtube-transcript-api`), which
     fetches the caption file, not a media stream.
   - Downloading media (via `yt-dlp` etc.) violates YouTube ToS, drags in the
     PoToken/bot-detection maintenance treadmill, and — for stored frames — adds
     a copyright-rehosting problem. We stay entirely on the captions side.
   - Consequence: if a video has no caption track, we currently do **not**
     process it. Show a clear "no captions available" state. (A targeted-Whisper
     fallback is a *future* discussion, not in scope now.)

2. **Visual moments via embedded player, NOT stored screenshots.**
   - For the "show me that part" feel, embed the YouTube IFrame player seeked to
     the timestamp. We store no frames → no copyright-rehosting exposure.
   - Frame extraction (download-required) is explicitly out of scope for v1.

3. **Never silently lose or alter source content.**
   - LLM transcript cleanup may fix obvious errors but must never invent or
     change meaning. The **raw caption is always kept as the bottom tier** of
     the document so any user can verify against the original.

## 4. Architecture / pipeline

```
YouTube URL
   │
   ▼
Cache check (by video ID) ──── hit ───▶ Serve cached doc (instant, no cost)
   │ miss
   ▼
Fetch captions            (no download · safe zone)
   ▼
Jargon detect + glossary  (shared pgvector store · reused across videos)
   ▼
LLM cleanup               (glossary-primed · raw transcript preserved)
   ▼
Sections + layered notes  (chapters or topic segmentation · TL;DR → sections → detail)
   ▼
Q&A index                 (RAG over notes + glossary)
   ▼
Interactive doc           (tiered notes · timestamp jumps · glossary panel · Q&A · embedded player)
```

Note the two ideas the diagram encodes: the whole flow stays in the safe zone
(captions in, document out), and **jargon-detect + LLM-cleanup are the only
stages that don't already exist in competitor tools** — that's the moat.

## 5. Tech stack

Matches the builder's existing stack — don't substitute without reason.

- **Frontend:** Next.js (App Router) + Tailwind + shadcn/ui. Renders the
  interactive doc: tiered/collapsible notes, glossary side panel, timestamp
  jump links, embedded YouTube IFrame player, Q&A box.
- **Backend API:** FastAPI (async, SQLAlchemy 2.x async).
- **Queue / worker:** Redis + an async worker (arq or Celery). Processing is
  slow and MUST be backgrounded — the API enqueues a job and returns a job id;
  the frontend polls/streams status. Do not process inline in the request.
- **DB:** PostgreSQL + **pgvector** (glossary embeddings + RAG embeddings).
- **External:** an LLM API for cleanup / jargon / summaries / Q&A;
  `youtube-transcript-api` (or equivalent) for captions.

## 6. Data model (starting sketch)

```
videos
  id (pk)
  youtube_id            (unique — THIS is the cache key)
  title, channel, duration_s, lang
  status                (queued | processing | ready | failed | no_captions)
  created_at, processed_at

transcripts
  id (pk)
  video_id (fk)
  raw_segments          (jsonb: [{start_s, end_s, text}] — original, untouched)
  cleaned_segments      (jsonb: same shape, cleaned — TIMESTAMPS PRESERVED)

sections
  id (pk)
  video_id (fk)
  idx, title, start_s, end_s
  summary_short         (one-liner)
  summary_full          (section detail)

doc_summaries
  video_id (fk)
  tldr                  (5-line top tier)

glossary_terms          (SHARED across all videos — this compounds over time)
  id (pk)
  term                  (normalized, e.g. "relu")
  display               ("ReLU")
  definition_beginner   (plain-English)
  embedding             (vector — pgvector)
  domain                (optional tag, e.g. "ml")
  created_at

term_occurrences        (links a video's text to glossary entries)
  id (pk)
  video_id (fk), term_id (fk)
  section_id (fk), char_offset / segment_ref

rag_chunks              (for Q&A)
  id (pk)
  video_id (fk)
  text, embedding (vector), start_s, end_s

jobs
  id (pk), video_id (fk), state, error, created_at, updated_at
```

The **shared `glossary_terms` table is a key design point**: terms recur across
videos ("kernel", "ReLU" appear in every CNN tutorial). Define once, reuse
everywhere. The glossary gets richer and cheaper per video over time.

## 7. Build phases (ship in this order)

Each phase is independently useful and shippable. Order front-loads
differentiation, back-loads risk/cost.

### Phase 1 — end-to-end skeleton (no wedge yet)
Goal: a working URL-in → document-out loop you can actually use.
- [ ] FastAPI scaffold + async SQLAlchemy + Postgres + pgvector extension
- [ ] Redis + worker scaffold; API enqueues, returns job id; status endpoint
- [ ] Caption fetch + persist `raw_segments`
- [ ] Cache by `youtube_id` (return existing doc on hit)
- [ ] Naive sectioning: use YouTube chapters if present, else 1 section
- [ ] Single-tier summary per section (one LLM call)
- [ ] Next.js: submit URL, poll status, render doc with timestamp jump links +
      embedded IFrame player
- [ ] States: queued / processing / ready / failed / no_captions

### Phase 2 — the wedge (this is the actual product)
- [ ] Jargon detection: extract candidate terms (acronyms, capitalized phrases,
      noun chunks) → LLM filter "would a beginner not know this?" → generate
      beginner definition → upsert into shared `glossary_terms` (dedupe by
      normalized term; embed for semantic dedupe)
- [ ] LLM transcript cleanup, **glossary-primed** (see §8) → `cleaned_segments`,
      timestamps preserved
- [ ] Tiered notes: TL;DR → section summaries → full detail → raw transcript
      (collapsible / progressive disclosure in the UI)
- [ ] Glossary side panel UI: terms linked from their occurrences; hover/click
      to reveal the beginner definition

### Phase 3 — depth
- [ ] Q&A: RAG over `rag_chunks` + glossary (reuses pgvector)
- [ ] "Visual moments": embedded player seeked to key timestamps inline in the doc
- [ ] (Only if ever justified) frame extraction — but this exits the safe zone;
      treat as a separate, deliberate decision, not a quiet add-on.

## 8. Key engineering details & guardrails

**Glossary-primed cleanup (the clever bit).** The jargon glossary doubles as the
proofreader's answer key. Feed the expected term spellings for *this* video into
the cleanup prompt so the model corrects "re lu" → "ReLU" by matching a known
whitelist instead of guessing in a vacuum. Detect jargon BEFORE (or alongside)
cleanup so the term list exists to prime it.

**Cleanup prompt rules** (low temperature):
- Fix obvious transcription errors in technical terminology, punctuation, and
  capitalization ONLY.
- Never change meaning, never invent content.
- If a word is unclear and you're not confident, leave it unchanged.
- Prefer the provided known-term list for spelling of technical vocabulary.

**Hallucination is the dangerous failure mode.** This is a *trust* product —
a confident wrong "correction" is worse than a visibly garbled word, because the
user can't tell. Mitigations: low temp, constrained prompt, known-term priming,
and **always keep raw transcript accessible underneath**.

**Preserve timestamps.** Caption tracks are timestamped segments; the whole
timestamp-jump UI and section alignment depend on text staying tied to its time
codes. Do NOT dump the full transcript into one call and free-rewrite it — that
returns clean prose with timestamps gone. Clean *within* segments (or re-align
cleaned text back to original timings). Process chunk-wise.

**Cache the expensive outputs.** Cleaned transcript + glossary + summaries are
part of what's cached per `youtube_id`, NOT regenerated per user/request. The
real cost is LLM tokens, not hosting — caching is the primary cost defense.

**Datacenter-IP caption blocking.** YouTube rate-limits / blocks caption
requests from cloud provider IP ranges. Caption fetch may work locally but fail
in production. Plan for a residential/rotating proxy on the fetch step at any
real volume. Build the fetcher so the proxy/transport is swappable.

## 9. Hosting (where this runs)

App shape: easy frontend + easy DB + a **long-running background worker** (the
worker is what breaks "free" tiers — serverless times out: Vercel 5 min,
Netlify 60 s, too short for an hour of transcript).

Recommended free-ish split:
- **Frontend:** Vercel free Hobby (built for Next.js).
- **Postgres + pgvector:** Supabase or Neon free tier.
- **Redis:** Upstash free tier.
- **API + worker:** a single cheap VPS via Docker Compose is the cleanest path
  given long jobs (Hetzner ~€4/mo; Oracle Cloud always-free ARM VM if you can
  provision one). Render's free web service works for the API but spins down on
  idle and its always-on worker is paid.

Avoid Railway (free runtime removed; recent reliability issues) and Fly.io (no
free tier for new users) for the always-on pieces.

## 10. Non-goals / what NOT to build

- ❌ Don't download video or audio (ToS + maintenance + copyright). Captions only.
- ❌ Don't store screenshots/frames in v1. Use the embedded player for visuals.
- ❌ Don't compete on raw summary quality — that's the commodity we lose at.
  Compete on the glossary + learning structure.
- ❌ Don't process synchronously in the request path. Always background it.
- ❌ Don't free-rewrite the transcript in one call (destroys timestamps).
- ❌ Don't regenerate cached outputs per request.

## 11. Open decisions (flag, don't silently pick)

- LLM provider/model for cleanup vs. jargon vs. Q&A (cost/quality tradeoff per task).
- Auth: anonymous + rate limit, or require login? (Affects cost control at scale.)
- Job status transport: simple polling vs. SSE/websocket streaming.
- Semantic dedupe threshold for glossary terms (avoid near-duplicate entries).
