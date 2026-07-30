"""Gatekeeper: decide up-front whether a video is something Gloss can teach from.

Gloss is strictly for tutorial/lecture/study content. A music video produces
lyric-noise notes; a "100 interview questions" compilation has answers but no
teaching narrative. Both would burn tokens and produce a useless doc, so we
reject them at the very first pipeline stage with a clear, user-facing reason.

Two layers:
1. Free heuristics on the captions (music markers, speech density) — catches
   music/ambient videos without any LLM call.
2. One small LLM classification (title + channel + transcript windows) for
   everything else.
"""

import re
from dataclasses import dataclass

from app.services.captions import CaptionSegment
from app.services.llm import _as_bool, _as_str, _transcript_windows, chat_json
from app.services.llm_context import llm_available

MUSIC_MARKER_RE = re.compile(r"\[(music|applause|singing)\]|♪|♫", re.IGNORECASE)

ACCEPT_CATEGORIES = {"tutorial", "lecture", "course", "educational_talk", "explainer"}


@dataclass
class GateVerdict:
    suitable: bool
    category: str
    reason: str  # user-facing, one sentence


def music_heuristic(segments: list[CaptionSegment], duration_s: int | None) -> GateVerdict | None:
    """Reject obvious music/ambient videos from caption shape alone. None = inconclusive."""
    if not segments:
        return None
    marker_hits = sum(1 for s in segments if MUSIC_MARKER_RE.search(s.text))
    if marker_hits / len(segments) > 0.3:
        return GateVerdict(False, "music", "This looks like a music video — Gloss only works with tutorials and lectures.")

    if duration_s and duration_s >= 120:
        words = sum(len(s.text.split()) for s in segments)
        wpm = words / (duration_s / 60)
        # Teaching speech runs ~110-170 wpm; music/ambient captions are far sparser.
        if wpm < 40:
            return GateVerdict(
                False,
                "low_speech",
                "There isn't enough spoken teaching content in this video to build study notes from.",
            )
    return None


async def classify_video(
    title: str | None,
    channel: str | None,
    duration_s: int | None,
    transcript_text: str,
) -> GateVerdict:
    """LLM verdict: is this a structured teaching video Gloss should process?"""
    if not llm_available():
        # Without an LLM we can't judge — let it through rather than block dev usage.
        return GateVerdict(True, "unknown", "")

    sample = _transcript_windows(transcript_text, n=3, size=1200)
    minutes = round(duration_s / 60) if duration_s else "?"
    prompt = f"""Video title: {title or "(unknown)"}
Channel: {channel or "(unknown)"}
Duration: {minutes} minutes

Transcript samples (from start, middle, end):
{sample}

Gloss turns TEACHING videos into study documents. Classify this video.

ACCEPT only if the video structurally TEACHES a topic or skill: tutorial, lecture,
course, conceptual explainer, educational conference talk.

REJECT everything else, including:
- music videos / songs / lyric videos
- Q&A or interview-question COMPILATIONS (e.g. "100 interview questions with solutions")
  — listing questions and answers is not structured teaching
- podcasts, casual interviews, panel chats
- vlogs, entertainment, gaming, pranks, reactions
- news clips, trailers, product promos, motivational speeches

Return JSON:
{{"category": "tutorial|lecture|course|educational_talk|explainer|music|qa_compilation|podcast|entertainment|news|promo|other",
  "suitable": true/false,
  "reason": "ONE friendly sentence telling the user why (shown in the UI on rejection)"}}"""

    data = await chat_json(
        "You are a strict gatekeeper for an educational note-taking tool. Respond with valid JSON only.",
        prompt,
        # Generous for reasoning models: hidden thinking tokens share this budget.
        max_tokens=1200,
    )
    category = _as_str(data.get("category")).lower() or "other"
    suitable = _as_bool(data.get("suitable")) and category in ACCEPT_CATEGORIES
    reason = _as_str(data.get("reason"))
    if not suitable and not reason:
        reason = "This video doesn't look like a tutorial or lecture, so Gloss can't build study notes from it."
    return GateVerdict(suitable, category, reason)


async def check_video_suitability(
    title: str | None,
    channel: str | None,
    duration_s: int | None,
    segments: list[CaptionSegment],
    transcript_text: str,
) -> GateVerdict:
    """Full gate: free heuristics first, LLM classification second."""
    verdict = music_heuristic(segments, duration_s)
    if verdict is not None:
        return verdict
    return await classify_video(title, channel, duration_s, transcript_text)
