import asyncio
import json
import logging
import re

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.config import get_settings
from app.services.llm_context import get_llm_creds, llm_available
from app.services.usage_stats import record_llm_usage

logger = logging.getLogger(__name__)

# Errors that mean "this provider can't serve right now" — quota, overload (503),
# timeouts, connection loss. Any of them should trigger provider failover.
FAILOVER_ERRORS = (RateLimitError, InternalServerError, APITimeoutError, APIConnectionError)


def _tokens_from_response(response) -> int:
    usage = getattr(response, "usage", None)
    if not usage:
        return 0
    return int(getattr(usage, "total_tokens", 0) or 0)


async def _track_response(response) -> None:
    await record_llm_usage(_tokens_from_response(response))


def get_llm_client() -> AsyncOpenAI:
    settings = get_settings()
    creds = get_llm_creds()
    api_key = creds.api_key if creds else settings.openai_api_key
    base_url = creds.base_url if creds else settings.openai_base_url
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        # Free cloud tiers (Groq) throttle with 429 + retry-after (often just seconds).
        # A pipeline fires many calls into a small per-minute window, so be patient:
        # the SDK sleeps per the server's retry-after between attempts. A genuinely
        # dead provider still fails fast on connection errors.
        max_retries=6,
        timeout=float(settings.llm_timeout_s),
    )


def active_model() -> str:
    creds = get_llm_creds()
    return creds.model if creds else get_settings().openai_model


def get_fallback_client() -> AsyncOpenAI | None:
    settings = get_settings()
    # A user's own key gets no failover: the fallback provider is the server's
    # account, so silently spending it would defeat bring-your-own-key.
    if get_llm_creds() is not None:
        return None
    if not settings.fallback_configured:
        return None
    return AsyncOpenAI(
        api_key=settings.fallback_openai_api_key,
        base_url=settings.fallback_openai_base_url.rstrip("/"),
        max_retries=2,
        timeout=float(settings.llm_timeout_s),
    )


async def _create_chat(
    messages: list[dict],
    *,
    temperature: float,
    max_tokens: int,
    response_format: dict | None = None,
) -> str:
    """One completion with automatic provider failover.

    Primary provider first (with its own patient retries); if it is still
    rate-limited (e.g. Groq's daily cap), retry once on the fallback provider
    (e.g. Gemini) so quota exhaustion degrades to "slower/different model"
    instead of "everything fails".
    """
    settings = get_settings()
    primary_model = active_model()
    kwargs: dict = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if response_format:
        kwargs["response_format"] = response_format
    try:
        response = await get_llm_client().chat.completions.create(
            model=primary_model, **kwargs
        )
        await _track_response(response)
        return response.choices[0].message.content or ""
    except FAILOVER_ERRORS as primary_err:
        fallback = get_fallback_client()
        if fallback is None:
            raise
        # Try each fallback model in order — hot models (gemini-3.5-flash) can hit
        # transient 503 demand spikes; a boring lite model rides those out.
        last_err: Exception = primary_err
        for model in settings.fallback_model_list:
            logger.warning(
                "Primary LLM (%s) unavailable (%s) — failing over to %s",
                primary_model,
                type(primary_err).__name__,
                model,
            )
            try:
                response = await fallback.chat.completions.create(model=model, **kwargs)
                await _track_response(response)
                return response.choices[0].message.content or ""
            except FAILOVER_ERRORS as exc:
                last_err = exc
                continue
        raise last_err


async def chat_json(system: str, user: str, *, max_tokens: int = 2000) -> dict:
    """Call LLM and parse a JSON object response (with provider failover)."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        content = await _create_chat(
            messages, temperature=0.2, max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
    except FAILOVER_ERRORS:
        raise  # all providers exhausted — let callers handle/record it
    except Exception:
        # Some providers/models reject response_format — retry without it.
        content = await _create_chat(messages, temperature=0.2, max_tokens=max_tokens)
    return _loads_lenient(content or "{}")


async def chat_text(system: str, user: str, *, max_tokens: int = 1200) -> str:
    """Plain-text LLM call (used by the Ask feature; JSON not needed)."""
    content = await _create_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return content.strip()


def _loads_lenient(content: str) -> dict:
    """Parse JSON, tolerating code fences / prose around the object (small models)."""
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    fence = re.search(r"\{.*\}", content, re.DOTALL)
    if fence:
        try:
            data = json.loads(fence.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


# ── coercion helpers (small models return ragged shapes) ─────────────────────

def _as_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return ""
    return str(value).strip()


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return False


def _ts(seconds: float) -> str:
    total = int(max(0, seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


_MERMAID_STARTS = (
    "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
    "erDiagram", "gantt", "mindmap", "journey", "pie", "gitGraph", "timeline",
)


def _clean_mermaid(source: str) -> str:
    """Return valid-looking Mermaid source, or '' if it isn't a diagram.

    We never render un-vetted text as a diagram — a malformed block would throw in
    the browser. Only accept sources that begin with a known Mermaid diagram type,
    and sanitize the syntax mistakes LLMs habitually make.
    """
    source = source.strip()
    if source.startswith("```"):
        source = re.sub(r"^```[a-zA-Z]*\n?", "", source)
        source = re.sub(r"\n?```$", "", source).strip()
    if not source:
        return ""
    if not source.startswith(_MERMAID_STARTS):
        return ""
    # LLMs often emit `-->|label|>Target` — a stray '>' after the closing label pipe.
    # Valid Mermaid is `-->|label| Target`.
    source = re.sub(r"\|\s*>", "| ", source)
    # Literal "\n" sequences (escaped newlines from JSON-in-JSON) break the parser.
    source = source.replace("\\n", "\n")
    return source


def _fallback_section(section_title: str, transcript: str) -> dict:
    """Deterministic content when the LLM is unavailable or returns nothing usable.

    Auto-captions often have NO punctuation, so sentence-splitting can yield one
    multi-thousand-char "sentence" — cap each point at a readable length so a
    fallback never dumps a transcript wall into the notes.
    """
    sentences = re.split(r"(?<=[.!?])\s+", transcript.strip())
    points = [s.strip() for s in sentences if len(s.strip()) > 20][:4]
    points = [p if len(p) <= 220 else p[:220].rsplit(" ", 1)[0] + "…" for p in points]
    return {
        "headline": section_title,
        "explainer": "",
        "key_points": points,
        "walkthrough": [],
        "diagram": "",
    }


# ── pass 1: whole-video outline (the connective tissue) ──────────────────────

async def _generate_doc_summary(title: str | None, listing: str) -> dict:
    """Doc-level {teaches, prerequisites}. Bounded output, independent of section count.

    (The concept map is generated later from the actual section content — see
    generate_doc_extras — which yields a far more useful diagram than a title-only flow.)
    """
    prompt = f"""Video title: {title or "Untitled"}

The video's sections are listed below as "index. title :: start of transcript":

{listing}

Return a JSON object:
{{
  "teaches": "2-4 plain-language sentences on what a learner will understand or be able to do after this video",
  "prerequisites": ["a concept the viewer should already know", "..."]
}}

Ground everything in the actual sections; do not invent topics."""

    data = await chat_json(
        "You summarize what an educational video teaches. Respond with valid JSON only.",
        prompt,
        max_tokens=900,
    )
    return {
        "teaches": _as_str(data.get("teaches")),
        "prerequisites": [p for p in (_as_str(x) for x in _as_list(data.get("prerequisites"))) if p][:8],
    }


async def _generate_section_roles(
    title: str | None, listing: str, section_defs: list[dict]
) -> list[str]:
    """One short 'role in the story' per section. Output scales with section count."""
    n = len(section_defs)
    prompt = f"""Video title: {title or "Untitled"}

The video's sections are listed below as "index. title :: start of transcript":

{listing}

Return a JSON object {{"roles": [...]}} where "roles" has EXACTLY {n} short strings, in the
same order as the sections, each describing what that section contributes to the overall story.
Ground each in the actual section; do not invent."""

    # Scale the token budget with section count so a long video's roles never truncate.
    max_tokens = min(4000, 500 + 60 * n)
    data = await chat_json(
        "You outline how a video's sections connect. Respond with valid JSON only.",
        prompt,
        max_tokens=max_tokens,
    )
    roles = [_as_str(r) for r in _as_list(data.get("roles"))]
    if len(roles) < n:
        roles += [section_defs[i]["title"] for i in range(len(roles), n)]
    return roles[:n]


async def build_video_outline(
    title: str | None,
    section_defs: list[dict],
    section_inputs: list[tuple[str, str]],
) -> dict:
    """Global outline: {teaches, prerequisites[], roles[] (one per section), throughline(mermaid)}.

    Split into two bounded LLM calls — a doc-level summary and the per-section roles — so the
    user-facing summary can't be truncated away by a long video's role list (which crowded out
    teaches/prerequisites on 20+ section videos when done in a single capped call).
    """
    n = len(section_defs)
    if not llm_available() or n == 0:
        return {
            "teaches": "",
            "prerequisites": [],
            "roles": [d["title"] for d in section_defs],
            "throughline": "",
        }

    listing = "\n".join(
        f'{d["idx"]}. {d["title"]} :: {text[:280]}'
        for d, (_, text) in zip(section_defs, section_inputs)
    )
    summary = await _generate_doc_summary(title, listing)
    roles = await _generate_section_roles(title, listing, section_defs)
    return {**summary, "roles": roles}


# ── pass 2: per-section structured notes (context-aware, parallel) ───────────

async def generate_section_content(
    title: str | None,
    teaches: str,
    section_title: str,
    role_prev: str,
    role_this: str,
    role_next: str,
    transcript: str,
    feedback: str = "",
) -> dict:
    """Structured, connected notes for one section: headline + bullets + worked steps + diagram.

    `feedback` carries a verifier finding about a previous attempt ("your diagram had
    unbalanced brackets", "the explainer restated the bullets") into the retry prompt.
    """
    fallback = _fallback_section(section_title, transcript)
    if not llm_available() or not transcript.strip():
        return fallback

    feedback_block = (
        f"\nA previous attempt was rejected by a quality check. Problems to fix this time:\n{feedback}\n"
        if feedback
        else ""
    )
    prompt = f"""Video: {title or "Untitled"}{feedback_block}
What the whole video teaches: {teaches or "(infer from the transcript)"}

Write study notes for ONE section so a BEGINNER gets the end-to-end picture without watching.
- Previously: {role_prev or "(this is the start of the video)"}
- THIS section — "{section_title}": {role_this or ""}
- Coming next: {role_next or "(this is the end of the video)"}

Section transcript:
{transcript[:12000]}

Return a JSON object:
{{
  "headline": "one sentence: what THIS section establishes, written as if the reader followed the earlier sections",
  "explainer": "3-5 sentences that EXPLAIN this section to a beginner: give the whole picture, why it matters, and one concrete example or analogy so it clicks. This is the part that makes the bullets make sense.",
  "key_points": ["3-6 concrete takeaways, one idea each"],
  "walkthrough": [{{"text": "one step of a worked example / derivation / demo", "math": "LaTeX without $ delimiters, or empty", "code": "code snippet, or empty"}}],
  "diagram": "a Mermaid diagram that VISUALLY EXPLAINS this section, or empty"
}}

Rules:
- GROUNDING: Every fact, number, and name must come from the transcript. You MAY use general domain
  knowledge to clarify, structure, and add a helpful analogy — but never introduce claims, figures,
  or specifics the video did not state. When unsure, stay literal. (This is a trust product.)
- THE READER CANNOT SEE THE SCREEN. When the speaker points at something ("this 3", "as you can
  see here", "this diagram"), DESCRIBE the thing in words from the transcript's context
  (e.g. "a sloppily handwritten digit 3 shown as a 28×28-pixel image"). Never leave a reference
  to an unseen visual unresolved.
- "explainer" is the most important field: make the concept genuinely understandable, connected to
  what came before, with an example. Don't just restate the bullets.
- Define a term the FIRST time it appears (e.g. "etcd (the cluster's key-value store)").
- "diagram": build a diagram that helps someone SEE how the pieces relate — an architecture, a data/
  request flow, or a process. Use real relationships between the actual components discussed, NOT a
  list of headings. Prefer `flowchart TD`/`graph TB` with labelled edges, or `sequenceDiagram` for a
  request/response flow. Node labels must be concrete things from the section. Use "" only if the
  section is purely narrative with nothing spatial/relational to show.
  Example of the RIGHT idea: graph TB; Client-->|request| APIServer; APIServer-->|schedules| Pod; Pod-->|runs| Container
- Use "walkthrough" ONLY for an actual worked example/derivation/procedure; otherwise [].
- "math" is raw LaTeX (e.g. "\\frac{{\\partial d}}{{\\partial a}} = b")."""

    data = await chat_json(
        "You write connected, beginner-friendly study notes with genuinely explanatory diagrams. Respond with valid JSON only.",
        prompt,
        # Generous: reasoning models spend hidden thinking tokens from this same budget.
        max_tokens=3200,
    )

    headline = _as_str(data.get("headline")) or fallback["headline"]
    key_points = [p for p in (_as_str(x) for x in _as_list(data.get("key_points"))) if p][:8]

    walkthrough: list[dict] = []
    for step in _as_list(data.get("walkthrough"))[:12]:
        if isinstance(step, dict):
            text, math, code = _as_str(step.get("text")), _as_str(step.get("math")), _as_str(step.get("code"))
        else:
            text, math, code = _as_str(step), "", ""
        if text or math or code:
            walkthrough.append({"text": text, "math": math, "code": code})

    if not key_points and not walkthrough:
        key_points = fallback["key_points"]

    return {
        "headline": headline,
        "explainer": _as_str(data.get("explainer")),
        "key_points": key_points,
        "walkthrough": walkthrough,
        "diagram": _clean_mermaid(_as_str(data.get("diagram"))),
    }


async def generate_sections(
    title: str | None,
    outline: dict,
    section_defs: list[dict],
    section_inputs: list[tuple[str, str]],
) -> list[dict]:
    """Run every section's structured summary concurrently, each primed with neighbor roles."""
    settings = get_settings()
    roles = outline.get("roles", [])
    teaches = outline.get("teaches", "")
    sem = asyncio.Semaphore(max(1, settings.llm_concurrency))

    def role_at(i: int) -> str:
        return roles[i] if 0 <= i < len(roles) else ""

    async def run_one(i: int) -> dict:
        _, text = section_inputs[i]
        async with sem:
            return await generate_section_content(
                title,
                teaches,
                section_defs[i]["title"],
                role_at(i - 1),
                role_at(i),
                role_at(i + 1),
                text,
            )

    return list(await asyncio.gather(*[run_one(i) for i in range(len(section_defs))]))


# ── document-level overview (assembled from the outline; no extra LLM call) ──

def build_document_overview(
    outline: dict,
    section_defs: list[dict],
    headlines: list[str],
) -> dict:
    """Doc-level content: 'what you'll learn' + prerequisites + timestamped nav.

    The richer fields (summary, concept_map, commands, notes, qa) are added by
    generate_doc_extras and merged on top of this in the worker.
    """
    nav = [
        {"t": d["start_s"], "label": d["title"], "one_liner": headline}
        for d, headline in zip(section_defs, headlines)
    ]
    return {
        "teaches": outline.get("teaches", ""),
        "prerequisites": outline.get("prerequisites", []),
        "nav": nav,
    }


def nav_to_tldr_text(nav: list[dict]) -> str:
    """Plain-text timestamped TL;DR (kept for backward compat + stale-doc detection)."""
    return "\n".join(f"- [{_ts(item['t'])}] {item['label']}: {item['one_liner']}" for item in nav)


def key_points_to_text(key_points: list[str]) -> str:
    """Plain-text fallback stored in summary_full."""
    return "\n".join(f"- {p}" for p in key_points)


# ── pass 3: document digest (standalone summary, concept map, commands, notes, Q&A) ──

def _section_briefs(section_defs: list[dict], section_contents: list[dict]) -> str:
    """Compact, grounded digest of the generated sections to feed doc-level prompts."""
    lines = []
    for d, c in zip(section_defs, section_contents):
        kp = "; ".join(c.get("key_points", [])[:4])
        lines.append(f'[{_ts(d["start_s"])}] {d["title"]}: {c.get("headline", "")} — {kp}')
    return "\n".join(lines)


async def _generate_key_summary(title: str | None, teaches: str, briefs: str) -> dict:
    prompt = f"""Video: {title or "Untitled"}
This video teaches: {teaches}

Section digest (grounded facts):
{briefs}

Write a STANDALONE end-to-end summary for someone who will read ONLY this and skip everything else.
Return JSON:
{{
  "summary": ["6-10 key-takeaway bullets that together tell the whole story, in order"],
  "concept_map": "a single Mermaid diagram showing how the video's MAIN CONCEPTS relate (architecture or flow), or empty"
}}

Rules:
- Ground strictly in the digest; invent no facts. The bullets must stand on their own.
- "concept_map": real, labelled relationships between the main concepts — NOT a list of section titles.
  e.g. graph TB; User-->|kubectl apply| APIServer; APIServer-->Scheduler; Scheduler-->|places| Pod"""
    data = await chat_json(
        "You write standalone executive summaries with a real concept map. Respond with valid JSON only.",
        prompt,
        max_tokens=1600,
    )
    return {
        "summary": [p for p in (_as_str(x) for x in _as_list(data.get("summary"))) if p][:12],
        "concept_map": _clean_mermaid(_as_str(data.get("concept_map"))),
    }


async def _generate_notes(title: str | None, briefs: str) -> list[dict]:
    prompt = f"""Video: {title or "Untitled"}

Section digest (grounded facts):
{briefs}

Write clean study notes the way a sharp student jots them while watching — grouped by topic,
short phrases, arrows/colons are fine. Return JSON:
{{"notes": [{{"heading": "topic", "bullets": ["short note", "short note"]}}]}}

Ground strictly in the digest; invent no facts."""
    data = await chat_json("You take concise, well-organised study notes. Respond with valid JSON only.", prompt, max_tokens=2200)
    notes: list[dict] = []
    for item in _as_list(data.get("notes")):
        if isinstance(item, dict):
            heading = _as_str(item.get("heading"))
            bullets = [b for b in (_as_str(x) for x in _as_list(item.get("bullets"))) if b][:10]
            if heading or bullets:
                notes.append({"heading": heading, "bullets": bullets})
    return notes[:24]


async def _generate_qa(title: str | None, briefs: str) -> list[dict]:
    prompt = f"""Video: {title or "Untitled"}

Section digest (grounded facts):
{briefs}

Write questions that (a) check a beginner's understanding and (b) could come up in an interview.
Return JSON:
{{"qa": [{{"question": "...", "answer": "2-4 sentence answer", "kind": "understanding" or "interview"}}]}}

8-12 items, a mix of both kinds. Ground answers in the digest + standard domain knowledge;
invent no specifics the video didn't cover."""
    data = await chat_json("You write comprehension and interview Q&A. Respond with valid JSON only.", prompt, max_tokens=2800)
    qa: list[dict] = []
    for item in _as_list(data.get("qa")):
        if isinstance(item, dict):
            q, a = _as_str(item.get("question")), _as_str(item.get("answer"))
            kind = _as_str(item.get("kind")).lower()
            kind = kind if kind in ("understanding", "interview") else "understanding"
            if q and a:
                qa.append({"question": q, "answer": a, "kind": kind})
    return qa[:16]


def _transcript_windows(text: str, n: int = 3, size: int = 6000) -> str:
    """Sample n windows spread across the transcript, so late-video content (e.g. the
    demo where commands are actually run) isn't cut off by a prefix-only excerpt."""
    if len(text) <= n * size:
        return text
    step = (len(text) - size) // (n - 1)
    return "\n[...]\n".join(text[i * step : i * step + size] for i in range(n))


async def _extract_commands(title: str | None, transcript: str) -> list[dict]:
    prompt = f"""Video: {title or "Untitled"}

Transcript excerpts (sampled from across the whole video):
{_transcript_windows(transcript)}

Extract every concrete command / CLI invocation the video runs or tells you to run
(shell, kubectl, git, npm, docker, SQL, etc.). Return JSON:
{{"commands": [{{"cmd": "the exact command", "purpose": "what it does, short"}}]}}

Only include commands actually present or explicitly described in the transcript.
If there are none, return {{"commands": []}}. Do NOT invent commands."""
    data = await chat_json("You extract CLI commands into a cheat-sheet. Respond with valid JSON only.", prompt, max_tokens=1500)
    cmds: list[dict] = []
    for item in _as_list(data.get("commands")):
        if isinstance(item, dict):
            cmd = _as_str(item.get("cmd"))
            if cmd:
                cmds.append({"cmd": cmd, "purpose": _as_str(item.get("purpose"))})
    return cmds[:40]


async def generate_doc_extras(
    title: str | None,
    teaches: str,
    section_defs: list[dict],
    section_contents: list[dict],
    transcript: str,
) -> dict:
    """Standalone summary + concept map + commands + notes + Q&A, from the generated sections.

    Each call is independent and failure-tolerant (a dropped call just yields an empty field),
    and they share the concurrency semaphore to respect free-tier rate limits.
    """
    empty = {"summary": [], "concept_map": "", "commands": [], "notes": [], "qa": []}
    settings = get_settings()
    if not llm_available() or not section_contents:
        return empty

    briefs = _section_briefs(section_defs, section_contents)
    sem = asyncio.Semaphore(max(1, settings.llm_concurrency))

    async def guarded(coro):
        async with sem:
            try:
                return await coro
            except Exception:
                return None

    key_summary, notes, qa, commands = await asyncio.gather(
        guarded(_generate_key_summary(title, teaches, briefs)),
        guarded(_generate_notes(title, briefs)),
        guarded(_generate_qa(title, briefs)),
        guarded(_extract_commands(title, transcript)),
    )
    key_summary = key_summary or {"summary": [], "concept_map": ""}
    return {
        "summary": key_summary.get("summary", []),
        "concept_map": key_summary.get("concept_map", ""),
        "notes": notes or [],
        "qa": qa or [],
        "commands": commands or [],
    }
