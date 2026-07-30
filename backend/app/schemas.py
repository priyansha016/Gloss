from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SubmitVideoRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=512)
    force_reprocess: bool = False


class SubmitVideoResponse(BaseModel):
    video_id: UUID
    job_id: UUID | None = None
    cached: bool
    status: str


class JobResponse(BaseModel):
    id: UUID
    video_id: UUID
    state: str
    error: str | None
    progress: str | None = None
    video_status: str
    created_at: datetime
    updated_at: datetime


class AskTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    # Prior turns (oldest first) so follow-ups keep their context; capped server-side.
    history: list[AskTurn] = Field(default_factory=list, max_length=12)


class AskSource(BaseModel):
    title: str
    start_s: float


class AskResponse(BaseModel):
    answer: str
    sources: list[AskSource]


class PracticeRequest(BaseModel):
    kind: str = Field(..., pattern="^(flashcards|quiz)$")


class PracticeResponse(BaseModel):
    kind: str
    cards: list[dict] = []
    questions: list[dict] = []
    cached: bool = False


class TranscriptSegmentSchema(BaseModel):
    start_s: float
    end_s: float
    text: str


class SectionSchema(BaseModel):
    id: UUID
    idx: int
    title: str
    start_s: float
    end_s: float
    summary_short: str | None
    summary_full: str | None
    content: dict | None = None


class GlossaryTermSchema(BaseModel):
    id: UUID
    term: str
    display: str
    definition_beginner: str
    domain: str | None


class TermOccurrenceSchema(BaseModel):
    term_id: UUID
    section_id: UUID | None
    segment_idx: int | None


class VideoDocumentResponse(BaseModel):
    id: UUID
    youtube_id: str
    title: str | None
    channel: str | None
    duration_s: int | None
    lang: str | None
    status: str
    progress: str | None = None
    status_reason: str | None = None
    tldr: str | None
    overview: dict | None = None
    sections: list[SectionSchema]
    raw_segments: list[TranscriptSegmentSchema]
    cleaned_segments: list[TranscriptSegmentSchema]
    glossary: list[GlossaryTermSchema]
    term_occurrences: list[TermOccurrenceSchema]

    model_config = {"from_attributes": True}


class ShowcaseVideoSchema(BaseModel):
    id: UUID
    youtube_id: str
    title: str | None
    channel: str | None
    duration_s: int | None


class AdminStatsResponse(BaseModel):
    videos_total: int
    videos_ready: int
    videos_processing: int
    videos_failed: int
    jobs_completed: int
    jobs_failed: int
    llm_calls: int
    llm_tokens: int
    recent_videos: list[ShowcaseVideoSchema]
