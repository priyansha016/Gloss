import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class VideoStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    no_captions = "no_captions"
    # Gatekeeper verdict: not a tutorial/lecture (music, Q&A compilation, vlog…)
    rejected = "rejected"


class JobState(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    youtube_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    channel: Mapped[str | None] = mapped_column(String(256))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    lang: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, name="video_status"),
        default=VideoStatus.queued,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    transcript: Mapped["Transcript | None"] = relationship(back_populates="video", uselist=False)
    sections: Mapped[list["Section"]] = relationship(back_populates="video", order_by="Section.idx")
    doc_summary: Mapped["DocSummary | None"] = relationship(back_populates="video", uselist=False)
    jobs: Mapped[list["Job"]] = relationship(back_populates="video")
    term_occurrences: Mapped[list["TermOccurrence"]] = relationship(back_populates="video")


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), unique=True)
    raw_segments: Mapped[list] = mapped_column(JSONB, default=list)
    cleaned_segments: Mapped[list | None] = mapped_column(JSONB)

    video: Mapped["Video"] = relationship(back_populates="transcript")


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512))
    start_s: Mapped[float] = mapped_column()
    end_s: Mapped[float] = mapped_column()
    summary_short: Mapped[str | None] = mapped_column(Text)
    summary_full: Mapped[str | None] = mapped_column(Text)
    # {headline, key_points[], walkthrough[{text, math, code}], diagram}
    content: Mapped[dict | None] = mapped_column(JSONB)

    video: Mapped["Video"] = relationship(back_populates="sections")


class DocSummary(Base):
    __tablename__ = "doc_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), unique=True)
    tldr: Mapped[str | None] = mapped_column(Text)
    # {teaches, prerequisites[], throughline(mermaid), nav[{t, label, one_liner}]}
    content: Mapped[dict | None] = mapped_column(JSONB)

    video: Mapped["Video"] = relationship(back_populates="doc_summary")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    state: Mapped[JobState] = mapped_column(Enum(JobState, name="job_state"), default=JobState.queued)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    video: Mapped["Video"] = relationship(back_populates="jobs")


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display: Mapped[str] = mapped_column(String(128))
    definition_beginner: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(768), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    occurrences: Mapped[list["TermOccurrence"]] = relationship(back_populates="glossary_term")


class TermOccurrence(Base):
    __tablename__ = "term_occurrences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("glossary_terms.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"))
    segment_idx: Mapped[int | None] = mapped_column(Integer)

    video: Mapped["Video"] = relationship(back_populates="term_occurrences")
    glossary_term: Mapped["GlossaryTerm"] = relationship(back_populates="occurrences")
    section: Mapped["Section | None"] = relationship()
