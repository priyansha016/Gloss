"""On-demand practice material: flashcards + quiz (NotebookLM-style).

Deliberately NOT part of the processing pipeline — generated the first time a user
asks (one LLM call each), then cached in doc_summaries.content so every later
request is free and instant. Grounded in the doc's own sections and glossary.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GlossaryTerm, Section, TermOccurrence, Video
from app.services.llm import _as_list, _as_str, chat_json

MAX_CARDS = 16
MAX_QUESTIONS = 10


def coerce_flashcards(data: dict) -> list[dict]:
    cards: list[dict] = []
    for item in _as_list(data.get("cards"))[:MAX_CARDS]:
        if not isinstance(item, dict):
            continue
        front, back = _as_str(item.get("front")), _as_str(item.get("back"))
        if front and back:
            cards.append({"front": front, "back": back})
    return cards


def coerce_quiz(data: dict) -> list[dict]:
    questions: list[dict] = []
    for item in _as_list(data.get("questions"))[:MAX_QUESTIONS]:
        if not isinstance(item, dict):
            continue
        q = _as_str(item.get("question"))
        options = [_as_str(o) for o in _as_list(item.get("options")) if _as_str(o)]
        try:
            answer = int(item.get("answer", -1))
        except (TypeError, ValueError):
            continue
        if q and len(options) == 4 and 0 <= answer < 4:
            questions.append(
                {
                    "question": q,
                    "options": options,
                    "answer": answer,
                    "explanation": _as_str(item.get("explanation")),
                }
            )
    return questions


async def _study_context(session: AsyncSession, video: Video) -> str:
    sections = (
        (await session.execute(select(Section).where(Section.video_id == video.id).order_by(Section.idx)))
        .scalars()
        .all()
    )
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
    lines = [f"Video: {video.title or 'Untitled'}"]
    for s in sections:
        c = s.content or {}
        points = "; ".join(c.get("key_points", [])[:5])
        lines.append(f"Section {s.idx} ({s.title}): {c.get('headline', '')} — {points}")
    if glossary:
        lines.append("Glossary: " + "; ".join(f"{g.display}: {g.definition_beginner}" for g in glossary[:14]))
    return "\n".join(lines)


async def generate_flashcards(session: AsyncSession, video: Video) -> list[dict]:
    context = await _study_context(session, video)
    prompt = f"""{context}

Create flashcards for spaced-repetition study of THIS video's content.
Return JSON: {{"cards": [{{"front": "a term, concept, or question", "back": "the concise answer/definition (1-3 sentences)"}}]}}

Rules:
- 10-{MAX_CARDS} cards, strictly grounded in the material above — no outside facts.
- Mix types: term→definition, concept→explanation, "why/how" prompts→answers.
- Fronts must be answerable from the back alone; backs must be self-contained."""
    data = await chat_json(
        "You write precise study flashcards. Respond with valid JSON only.",
        prompt,
        max_tokens=2600,
    )
    return coerce_flashcards(data)


async def generate_quiz(session: AsyncSession, video: Video) -> list[dict]:
    context = await _study_context(session, video)
    prompt = f"""{context}

Create a multiple-choice quiz testing understanding of THIS video's content.
Return JSON: {{"questions": [{{"question": "...", "options": ["A", "B", "C", "D"], "answer": <0-3>, "explanation": "why the right answer is right (1-2 sentences)"}}]}}

Rules:
- 6-{MAX_QUESTIONS} questions, strictly grounded in the material above — no outside facts.
- Exactly 4 options each; distractors must be plausible but clearly wrong per the video.
- Test understanding (why/how/what-happens-if), not just word recall.
- Vary the correct option's position across questions."""
    data = await chat_json(
        "You write fair, understanding-focused quizzes. Respond with valid JSON only.",
        prompt,
        max_tokens=3200,
    )
    return coerce_quiz(data)
