import json

from app.config import get_settings
from app.services.captions import CaptionSegment
from app.services.llm import chat_json
from app.services.llm_context import llm_available


def _segment_needs_cleanup(segment: CaptionSegment, known_terms: list[str]) -> bool:
    if not known_terms:
        return False
    lower = segment.text.lower()
    return any(term.lower() in lower for term in known_terms)


async def cleanup_segments(
    segments: list[CaptionSegment],
    known_terms: list[str],
) -> list[CaptionSegment]:
    """Glossary-primed cleanup only where jargon appears (skips most caption lines)."""
    settings = get_settings()
    if not llm_available() or not segments:
        return segments
    if settings.fast_processing or not known_terms:
        return segments

    indices_to_clean = [i for i, seg in enumerate(segments) if _segment_needs_cleanup(seg, known_terms)]
    if not indices_to_clean:
        return segments

    result = [
        CaptionSegment(start_s=seg.start_s, end_s=seg.end_s, text=seg.text)
        for seg in segments
    ]
    batch_size = 40
    term_list = ", ".join(sorted(set(known_terms))[:80])

    for offset in range(0, len(indices_to_clean), batch_size):
        batch_indices = indices_to_clean[offset : offset + batch_size]
        batch = [segments[i] for i in batch_indices]
        batch_map = {str(i): seg.text for i, seg in enumerate(batch)}
        prompt = f"""Fix obvious caption transcription errors in technical terminology, punctuation, and capitalization ONLY.

Known technical terms for this video (prefer these spellings):
{term_list}

Rules:
- Never change meaning. Never invent content.
- If unsure, leave text unchanged.
- Return JSON object mapping each segment index to cleaned text.
- Keep roughly the same length; do not merge or split segments.

Segments:
{json.dumps(batch_map, ensure_ascii=False)}"""

        fixes = await chat_json(
            "You proofread transcript segments. Respond with valid JSON only.",
            prompt,
            max_tokens=4000,
        )

        for local_i, global_i in enumerate(batch_indices):
            seg = segments[global_i]
            new_text = str(fixes.get(str(local_i), seg.text)).strip() or seg.text
            result[global_i] = CaptionSegment(start_s=seg.start_s, end_s=seg.end_s, text=new_text)

    return result
