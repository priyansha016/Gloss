"""Quality verifier: generate → critique → repair, bounded.

Runs at the end of the pipeline, before a doc is marked ready. Two layers:

1. Deterministic checks (free, instant): empty fields, malformed diagrams,
   missing commands for clearly CLI-heavy videos.
2. One LLM critic pass over the section digest: shallow explainers,
   meaningless diagrams, disconnected headlines, ungrounded claims.

Each finding triggers ONE targeted regeneration with the failure fed back into
the prompt (see `feedback` in generate_section_content). Anything still failing
after repair is degraded safely (bad diagram → dropped) and recorded in the
quality report stored on the doc — visible failure instead of silent shipping.
"""

import asyncio
import re
from dataclasses import dataclass

from app.config import get_settings
from app.services.embeddings import extract_candidate_terms, normalize_term
from app.services.llm import (
    _as_list,
    _as_str,
    _extract_commands,
    _generate_doc_summary,
    _generate_key_summary,
    _section_briefs,
    chat_json,
    generate_section_content,
)
from app.services.llm_context import llm_available

MAX_SECTION_REPAIRS = 6
CLI_HINT_RE = re.compile(
    r"\b(kubectl|minikube|docker|npm|pip|git clone|git commit|brew install|apt[- ]get|terraform|cargo|pytest)\b",
    re.IGNORECASE,
)


@dataclass
class Finding:
    section_idx: int  # -1 for doc-level findings
    field: str        # "explainer" | "key_points" | "diagram" | "headline" | doc-level names
    problem: str


# ── deterministic layer ───────────────────────────────────────────────────────

def mermaid_lint(source: str) -> str | None:
    """Cheap structural lint for issues that survive _clean_mermaid. None = OK."""
    if not source:
        return None
    for open_ch, close_ch in ("[]", "()", "{}"):
        if source.count(open_ch) != source.count(close_ch):
            return f"unbalanced {open_ch}{close_ch} brackets"
    if "-->" not in source and "---" not in source and "->>" not in source and not source.startswith(("pie", "mindmap", "timeline")):
        return "no edges — not a real diagram"
    return None


def transcript_looks_cli(transcript: str) -> bool:
    """True when the video clearly demonstrates command-line usage."""
    return len(CLI_HINT_RE.findall(transcript)) >= 3


ACRONYM_LIKE_RE = re.compile(r"^[A-Za-z]*[A-Z]{2,}[A-Za-z0-9]*$|^[A-Z][a-z]+[A-Z]")


def _notes_text(content: dict) -> str:
    parts = [
        _as_str(content.get("headline")),
        _as_str(content.get("explainer")),
        " ".join(_as_str(p) for p in _as_list(content.get("key_points"))),
        " ".join(_as_str(w.get("text")) for w in _as_list(content.get("walkthrough")) if isinstance(w, dict)),
    ]
    return normalize_term(" ".join(parts))


def find_coverage_gaps(section_transcript: str, content: dict) -> list[str]:
    """Concepts the section transcript clearly teaches but the notes never mention.

    Summarizing means condensing — NOT skipping what the video teaches (e.g. a section
    that explains ReLU must mention ReLU). Heuristic: candidate technical terms that
    recur in the transcript (or are named-concept acronyms like ReLU/YAML appearing
    even once) must appear somewhere in the generated notes.
    """
    if not section_transcript.strip():
        return []
    notes = _notes_text(content)
    transcript_lower = section_transcript.lower()
    missed: list[str] = []
    for term in extract_candidate_terms(section_transcript, limit=15):
        norm = normalize_term(term)
        if not norm or norm in notes:
            continue
        count = transcript_lower.count(norm.lower()) or transcript_lower.count(term.lower())
        # Named concepts (ReLU, YAML) matter at a single mention; plain words need to
        # genuinely recur (4+) before we insist — cuts noise like "Case"/"Three".
        threshold = 1 if (ACRONYM_LIKE_RE.match(term) and len(norm) >= 3) else 4
        if count >= threshold:
            missed.append(term)
    return missed[:5]


def find_section_issues(section_contents: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    for i, content in enumerate(section_contents):
        if not _as_str(content.get("explainer")):
            findings.append(Finding(i, "explainer", "the beginner explainer is missing"))
        points = _as_list(content.get("key_points"))
        if not points:
            findings.append(Finding(i, "key_points", "key points are missing"))
        elif any(len(_as_str(p)) > 400 for p in points):
            # A "key point" thousands of chars long is raw transcript leaking through
            # (fallback on unpunctuated auto-captions) — not a summary at all.
            findings.append(
                Finding(i, "key_points", "key points contain raw transcript text instead of concise takeaways")
            )
        lint = mermaid_lint(_as_str(content.get("diagram")))
        if lint:
            findings.append(Finding(i, "diagram", f"the Mermaid diagram is invalid: {lint}"))
    return findings


def find_overview_issues(extras: dict, teaches: str, transcript: str) -> list[Finding]:
    findings: list[Finding] = []
    if not teaches.strip():
        findings.append(Finding(-1, "teaches", "the 'what you'll learn' summary is empty"))
    if not extras.get("summary"):
        findings.append(Finding(-1, "summary", "the key-takeaways summary is empty"))
    lint = mermaid_lint(_as_str(extras.get("concept_map")))
    if lint:
        findings.append(Finding(-1, "concept_map", f"concept map invalid: {lint}"))
    if not extras.get("commands") and transcript_looks_cli(transcript):
        findings.append(Finding(-1, "commands", "video demonstrates CLI commands but none were extracted"))
    return findings


# ── LLM critic layer (one call) ───────────────────────────────────────────────

async def critique_sections(
    title: str | None,
    section_defs: list[dict],
    section_contents: list[dict],
) -> list[Finding]:
    """Single critic pass judging quality (not just presence) of the generated notes."""
    if not llm_available() or not section_contents:
        return []

    digest_lines = []
    for d, c in zip(section_defs, section_contents):
        digest_lines.append(
            f'--- section {d["idx"]}: {d["title"]}\n'
            f'headline: {c.get("headline", "")}\n'
            f'explainer: {c.get("explainer", "")[:400]}\n'
            f'diagram: {(c.get("diagram") or "(none)")[:200]}'
        )
    digest = "\n".join(digest_lines)

    prompt = f"""Video: {title or "Untitled"}

You are the quality reviewer for generated study notes. Below is a digest of each section.

{digest}

Flag ONLY real quality failures (be strict but do not nitpick):
- explainer that merely restates facts without explaining the end-to-end picture to a beginner
- diagram that is just a list of names/titles without meaningful relationships
- headline that reads standalone/disconnected from a flowing document
- references to on-screen visuals that are never described (e.g. "the low-resolution 3",
  "as shown here") — the reader cannot see the video, so the thing must be described in words

Return JSON: {{"findings": [{{"section": <idx>, "field": "explainer"|"diagram"|"headline", "problem": "one specific sentence"}}]}}
Return {{"findings": []}} if quality is acceptable. At most 6 findings — worst first."""

    data = await chat_json(
        "You are a strict but fair quality reviewer of study notes. Respond with valid JSON only.",
        prompt,
        # Generous for reasoning models: hidden thinking tokens share this budget.
        max_tokens=1800,
    )
    findings: list[Finding] = []
    valid_fields = {"explainer", "diagram", "headline"}
    for item in _as_list(data.get("findings"))[:6]:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("section", -99))
        except (TypeError, ValueError):
            continue
        field = _as_str(item.get("field"))
        problem = _as_str(item.get("problem"))
        if 0 <= idx < len(section_contents) and field in valid_fields and problem:
            findings.append(Finding(idx, field, problem))
    return findings


# ── repair + entry points ─────────────────────────────────────────────────────

def _describe(f: Finding) -> str:
    where = "overview" if f.section_idx < 0 else f"section {f.section_idx}"
    return f"{where}/{f.field}: {f.problem}"


async def verify_sections(
    title: str | None,
    outline: dict,
    section_defs: list[dict],
    section_inputs: list[tuple[str, str]],
    section_contents: list[dict],
) -> tuple[list[dict], dict]:
    """Check + repair per-section content. Returns (repaired contents, quality report)."""
    findings = find_section_issues(section_contents)
    # Coverage: a section must mention the concepts its transcript actually teaches.
    for i, (_, text) in enumerate(section_inputs):
        missed = find_coverage_gaps(text, section_contents[i])
        if missed:
            findings.append(
                Finding(
                    i,
                    "coverage",
                    "the transcript teaches these concepts but the notes never mention them: "
                    f"{', '.join(missed)} — cover the ones that are actually taught (do not skip "
                    "important material for brevity)",
                )
            )
    try:
        findings += await critique_sections(title, section_defs, section_contents)
    except Exception:
        pass  # critic is best-effort; deterministic findings still apply

    if not findings:
        return section_contents, {"fixed": [], "unresolved": []}

    # One regeneration per section, all of its findings merged into one feedback string.
    by_section: dict[int, list[Finding]] = {}
    for f in findings:
        by_section.setdefault(f.section_idx, []).append(f)

    roles = outline.get("roles", [])
    teaches = outline.get("teaches", "")
    settings = get_settings()
    sem = asyncio.Semaphore(max(1, settings.llm_concurrency))
    repaired = list(section_contents)
    fixed: list[str] = []
    unresolved: list[str] = []

    def role_at(i: int) -> str:
        return roles[i] if 0 <= i < len(roles) else ""

    async def repair_one(idx: int, section_findings: list[Finding]) -> None:
        feedback = "\n".join(f"- {f.field}: {f.problem}" for f in section_findings)
        _, text = section_inputs[idx]
        try:
            async with sem:
                new_content = await generate_section_content(
                    title, teaches, section_defs[idx]["title"],
                    role_at(idx - 1), role_at(idx), role_at(idx + 1),
                    text, feedback=feedback,
                )
        except Exception:
            unresolved.extend(_describe(f) for f in section_findings)
            return
        # Re-check: keep the repair only where it actually fixed the problem.
        still_bad = {f.field for f in find_section_issues([new_content])}
        if any(f.field == "coverage" for f in section_findings) and find_coverage_gaps(text, new_content):
            still_bad.add("coverage")
        for f in section_findings:
            (unresolved if f.field in still_bad else fixed).append(_describe(f))
        if "diagram" in still_bad:
            new_content["diagram"] = ""  # degrade safely: no diagram beats a broken one
        repaired[idx] = new_content

    section_batches = list(by_section.items())
    await asyncio.gather(
        *[repair_one(idx, fs) for idx, fs in section_batches[:MAX_SECTION_REPAIRS]]
    )
    for _, section_findings in section_batches[MAX_SECTION_REPAIRS:]:
        unresolved.extend(_describe(f) for f in section_findings)
    return repaired, {"fixed": fixed, "unresolved": unresolved}


async def verify_overview(
    title: str | None,
    outline: dict,
    section_defs: list[dict],
    section_inputs: list[tuple[str, str]],
    section_contents: list[dict],
    extras: dict,
    transcript: str,
) -> tuple[dict, dict, dict]:
    """Check + repair doc-level content. Returns (outline, extras, quality report)."""
    findings = find_overview_issues(extras, outline.get("teaches", ""), transcript)
    if not findings:
        return outline, extras, {"fixed": [], "unresolved": []}

    fixed: list[str] = []
    unresolved: list[str] = []
    listing = "\n".join(
        f'{d["idx"]}. {d["title"]} :: {text[:280]}'
        for d, (_, text) in zip(section_defs, section_inputs)
    )
    briefs = _section_briefs(section_defs, section_contents)

    for f in findings:
        try:
            if f.field == "teaches":
                summary = await _generate_doc_summary(title, listing)
                if summary.get("teaches"):
                    outline = {**outline, **summary}
                    fixed.append(_describe(f))
                else:
                    unresolved.append(_describe(f))
            elif f.field in ("summary", "concept_map"):
                key = await _generate_key_summary(title, outline.get("teaches", ""), briefs)
                if f.field == "summary" and key.get("summary"):
                    extras["summary"] = key["summary"]
                    fixed.append(_describe(f))
                elif f.field == "concept_map" and not mermaid_lint(key.get("concept_map", "")):
                    extras["concept_map"] = key.get("concept_map", "")
                    fixed.append(_describe(f))
                else:
                    if f.field == "concept_map":
                        extras["concept_map"] = ""  # degrade safely
                    unresolved.append(_describe(f))
            elif f.field == "commands":
                commands = await _extract_commands(title, transcript)
                if commands:
                    extras["commands"] = commands
                    fixed.append(_describe(f))
                else:
                    unresolved.append(_describe(f))
        except Exception:
            unresolved.append(_describe(f))

    return outline, extras, {"fixed": fixed, "unresolved": unresolved}
