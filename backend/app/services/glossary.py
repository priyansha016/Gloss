import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GlossaryTerm
from app.services.embeddings import embed_text, extract_candidate_terms, normalize_term
from app.services.llm import _transcript_windows, chat_json
from app.services.llm_context import llm_available
from app.config import get_settings

AMBIGUOUS_TERMS = {
    "service",
    "node",
    "application",
    "component",
    "database",
    "config",
    "secret",
    "deployment",
    "cluster",
}

CHAPTER_SPLIT_RE = re.compile(r"[&/,+\-–—]")


@dataclass
class JargonTerm:
    display: str
    definition_beginner: str
    domain: str | None = None


def extract_chapter_terms(chapter_titles: list[str]) -> list[str]:
    """Pull likely technical terms from YouTube chapter titles."""
    seen: set[str] = set()
    terms: list[str] = []
    for title in chapter_titles:
        for part in CHAPTER_SPLIT_RE.split(title):
            cleaned = re.sub(r"[^A-Za-z0-9\s-]", " ", part).strip()
            for token in cleaned.split():
                norm = normalize_term(token)
                if len(norm) < 3 or norm in seen:
                    continue
                seen.add(norm)
                terms.append(token if token.isupper() else token.capitalize())
    return terms


def _term_in_text(display: str, text: str) -> bool:
    if not display or not text:
        return False
    return bool(re.search(rf"\b{re.escape(display)}\b", text, re.IGNORECASE))


def is_term_relevant_in_section(
    display: str,
    *,
    section_title: str,
    section_summary: str,
    section_text: str,
) -> bool:
    """Avoid linking generic English words unless the section is actually about them."""
    if _term_in_text(display, section_title) or _term_in_text(display, section_summary):
        return True
    if display.lower() not in AMBIGUOUS_TERMS:
        return display.lower() in section_text.lower()
    return False


async def detect_jargon(
    transcript_text: str,
    video_title: str | None = None,
    chapter_titles: list[str] | None = None,
) -> list[JargonTerm]:
    """Find beginner-unfriendly terms and plain-English definitions."""
    settings = get_settings()
    candidates = extract_candidate_terms(transcript_text)
    if not candidates or not llm_available():
        return []

    max_terms = 12 if settings.fast_processing else settings.max_glossary_terms
    sample_len = 6000 if settings.fast_processing else 14000
    candidate_count = 40 if settings.fast_processing else 60

    # Sample windows across the WHOLE video — a prefix-only sample never sees terms
    # introduced later (e.g. ReLU taught at minute 12 of a 24-minute video).
    sample = _transcript_windows(transcript_text, n=3, size=sample_len // 3)
    candidate_blob = ", ".join(candidates[:candidate_count])
    title_line = f"Video title: {video_title}\n" if video_title else ""
    chapter_terms = extract_chapter_terms(chapter_titles or [])
    chapter_line = ""
    if chapter_titles:
        chapter_line = "Chapter titles:\n" + "\n".join(f"- {t}" for t in chapter_titles[:20]) + "\n"
    if chapter_terms:
        chapter_line += f"Terms from chapters (must include if technical): {', '.join(chapter_terms)}\n"

    prompt = f"""{title_line}{chapter_line}You are building a beginner glossary for an educational video transcript.

Candidate terms (heuristic extract):
{candidate_blob}

Transcript sample:
{sample}

Return JSON object with key "terms": an array of up to {max_terms} items.
Each item: {{"display": "Proper spelling", "definition_beginner": "1-2 plain sentences", "domain": "optional short tag"}}

Rules:
- ONLY include terms a beginner likely would NOT know.
- Skip common English and generic tutorial words.
- INCLUDE technical tools, CLI commands, frameworks/libraries, methodologies and acronyms — even
  lowercase ones (e.g. kubectl, minikube, etcd, kubelet, DevOps, CI/CD, YAML, API server). These are
  exactly the terms beginners get stuck on, so do not skip them for being lowercase or command-like.
- Skip chapter titles and speaker names unless they are technical concepts.
- Definitions must match how the term is used in THIS video (use the video title and chapters for context).
- For domain-specific tools (e.g. Kubernetes, Python, biology), define terms in that domain — not everyday English meanings.
- Do NOT use misleading analogies (e.g. do not compare a Kubernetes Service to a restaurant waiter).
- Include important terms from chapter titles (e.g. Ingress, Pod, ConfigMap) even if they appear briefly.
- Definitions must not use other unexplained jargon.
- Prefer terms actually used in the transcript."""

    data = await chat_json(
        "You extract technical jargon for beginners. Respond with valid JSON only.",
        prompt,
        max_tokens=2500,
    )

    terms: list[JargonTerm] = []
    for item in data.get("terms", []):
        display = str(item.get("display", "")).strip()
        definition = str(item.get("definition_beginner", "")).strip()
        if not display or not definition:
            continue
        terms.append(
            JargonTerm(
                display=display,
                definition_beginner=definition,
                domain=(str(item.get("domain")).strip() or None) if item.get("domain") else None,
            )
        )

    if terms:
        return terms[:max_terms]

    # Fallback: ask LLM to define top repeated candidates directly
    if len(candidates) >= 3:
        fallback_prompt = f"""{title_line}Define these technical terms from a lecture for a complete beginner.
Return JSON {{"terms": [{{"display": "...", "definition_beginner": "...", "domain": "..."}}]}} with up to {max_terms} items.

Terms: {", ".join(candidates[:max_terms])}"""
        fallback = await chat_json(
            "You write beginner glossary definitions. Respond with valid JSON only.",
            fallback_prompt,
            max_tokens=2000,
        )
        for item in fallback.get("terms", []):
            display = str(item.get("display", "")).strip()
            definition = str(item.get("definition_beginner", "")).strip()
            if display and definition:
                terms.append(
                    JargonTerm(
                        display=display,
                        definition_beginner=definition,
                        domain=(str(item.get("domain")).strip() or None) if item.get("domain") else None,
                    )
                )

    return terms[:max_terms]


async def upsert_glossary_term(
    session: AsyncSession,
    jargon: JargonTerm,
) -> GlossaryTerm:
    norm = normalize_term(jargon.display)
    existing = (
        await session.execute(select(GlossaryTerm).where(GlossaryTerm.term == norm))
    ).scalar_one_or_none()

    if existing:
        incoming = jargon.definition_beginner.strip()
        current = (existing.definition_beginner or "").strip()
        if len(incoming) > len(current) or (
            current and any(bad in current.lower() for bad in ("waiter", "restaurant", "think of it like"))
        ):
            existing.definition_beginner = incoming
        if jargon.domain and not existing.domain:
            existing.domain = jargon.domain
        if jargon.display and len(jargon.display) >= len(existing.display):
            existing.display = jargon.display
        return existing

    settings = get_settings()
    embedding = None
    if not settings.fast_processing:
        embedding = await embed_text(f"{jargon.display}: {jargon.definition_beginner}")
    term = GlossaryTerm(
        term=norm,
        display=jargon.display,
        definition_beginner=jargon.definition_beginner,
        embedding=embedding,
        domain=jargon.domain,
    )
    session.add(term)
    await session.flush()
    return term
