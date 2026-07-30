"""Ask-the-video: answer a user question grounded in the processed document.

v1 retrieval is lexical (keyword overlap between the question and each section's
title/summary/notes), which keeps context small enough for free-tier token budgets.
pgvector RAG over rag_chunks can replace the scorer later without changing the API.
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocSummary, GlossaryTerm, Section, TermOccurrence, Transcript, Video
from app.services.llm import chat_text

_STOP = set(
    "the a an and or of to in on for with is are was were be been being it this that "
    "what how why when where who which does do did can could should would you your "
    "i we they he she about into from as at by not".split()
)

MAX_SECTIONS = 3
EXCERPT_CHARS = 2500


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP}


def _ts(seconds: float) -> str:
    total = int(max(0, seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _section_text(section: Section) -> str:
    content = section.content or {}
    parts = [
        section.title,
        section.summary_short or "",
        content.get("explainer", ""),
        " ".join(content.get("key_points", [])),
    ]
    return " ".join(p for p in parts if p)


def _score_sections(question: str, sections: list[Section]) -> list[Section]:
    q_tokens = _tokens(question)
    scored = sorted(
        sections,
        key=lambda s: len(q_tokens & _tokens(_section_text(s))),
        reverse=True,
    )
    top = [s for s in scored if len(q_tokens & _tokens(_section_text(s))) > 0][:MAX_SECTIONS]
    return top or sections[:MAX_SECTIONS]


def _transcript_excerpt(segments: list[dict], start_s: float, end_s: float) -> str:
    text = " ".join(
        s["text"] for s in segments if s["start_s"] < end_s and s["end_s"] > start_s
    )
    return text[:EXCERPT_CHARS]


async def answer_question(
    session: AsyncSession,
    video: Video,
    question: str,
    history: list[dict] | None = None,
) -> dict:
    sections = (
        (await session.execute(select(Section).where(Section.video_id == video.id).order_by(Section.idx)))
        .scalars()
        .all()
    )
    doc_summary = (
        await session.execute(select(DocSummary).where(DocSummary.video_id == video.id))
    ).scalar_one_or_none()
    transcript = (
        await session.execute(select(Transcript).where(Transcript.video_id == video.id))
    ).scalar_one_or_none()
    glossary = (
        (
            await session.execute(
                select(GlossaryTerm)
                .join(TermOccurrence, TermOccurrence.term_id == GlossaryTerm.id)
                .where(TermOccurrence.video_id == video.id)
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    segments = []
    if transcript:
        segments = transcript.cleaned_segments or transcript.raw_segments or []

    overview = (doc_summary.content if doc_summary else None) or {}
    history = history or []

    # Follow-ups ("explain that more") carry little signal on their own — score
    # retrieval on the question PLUS the most recent user turn.
    prior_user = next((t["content"] for t in reversed(history) if t.get("role") == "user"), "")
    top_sections = _score_sections(f"{prior_user} {question}".strip(), list(sections))

    blocks: list[str] = []
    if overview.get("teaches"):
        blocks.append(f"What the video teaches: {overview['teaches']}")
    if overview.get("summary"):
        blocks.append("Key takeaways:\n" + "\n".join(f"- {s}" for s in overview["summary"][:10]))
    if glossary:
        defs = "\n".join(f"- {g.display}: {g.definition_beginner}" for g in glossary[:12])
        blocks.append(f"Glossary:\n{defs}")
    for s in top_sections:
        content = s.content or {}
        points = "\n".join(f"- {p}" for p in content.get("key_points", []))
        excerpt = _transcript_excerpt(segments, s.start_s, s.end_s)
        blocks.append(
            f"Section [{_ts(s.start_s)}] {s.title}:\n"
            f"{content.get('explainer', '')}\n{points}\n"
            f"Transcript excerpt: {excerpt}"
        )

    context = "\n\n".join(blocks)

    convo = ""
    if history:
        turns = "\n".join(f'{t.get("role", "user")}: {t.get("content", "")[:600]}' for t in history[-6:])
        convo = f"\nConversation so far (for context — resolve references like \"that\" or \"it\"):\n{turns}\n"

    prompt = f"""You are answering a question about one specific educational video, using ONLY the material below.

{context}
{convo}
Question: {question}

Rules:
- Answer from the material above. You may use general domain knowledge to phrase things clearly,
  but do not introduce facts, numbers, or claims the video did not cover.
- If the user just greets you or makes small talk, reply warmly in one sentence and invite them to
  ask something about this video.
- If the video does not cover the question, say so plainly and suggest the closest covered topic.
- Reference where in the video the answer comes from using timestamps like [{_ts(top_sections[0].start_s) if top_sections else "0:00"}].
- Be concise: 2-6 sentences unless a step list is genuinely needed."""

    answer = await chat_text(
        "You answer questions about a video from its notes and transcript, staying grounded.",
        prompt,
    )
    return {
        "answer": answer,
        "sources": [{"title": s.title, "start_s": s.start_s} for s in top_sections],
    }
