from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Request
from app.services.llm import FAILOVER_ERRORS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import llm_creds, require_admin, require_llm_creds
from app.config import get_settings
from app.db import get_db
from app.models import GlossaryTerm, Job, JobState, TermOccurrence, Video, VideoStatus
from app.schemas import (
    AdminStatsResponse,
    AskRequest,
    AskResponse,
    JobResponse,
    PracticeRequest,
    PracticeResponse,
    ShowcaseVideoSchema,
    SubmitVideoRequest,
    SubmitVideoResponse,
    VideoDocumentResponse,
)
from app.services.doc_quality import is_stale_document
from app.services.llm_context import get_llm_creds
from app.services.qa import answer_question
from app.services.ratelimit import RateLimit
from app.services.study_tools import generate_flashcards, generate_quiz
from app.services.usage_stats import get_llm_usage
from app.services.youtube import extract_youtube_id

router = APIRouter(prefix="/api")

_settings = get_settings()
_submit_limit = RateLimit("submit", _settings.rate_limit_submit_per_hour)
_ask_limit = RateLimit("ask", _settings.rate_limit_ask_per_hour)
_practice_limit = RateLimit("practice", _settings.rate_limit_practice_per_hour)


async def _enqueue_process(video_id: UUID) -> None:
    """Queue the pipeline, carrying the caller's LLM key into the worker process."""
    creds = get_llm_creds()
    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await redis.enqueue_job(
        "process_video", str(video_id), creds.as_dict() if creds else None
    )
    await redis.aclose()


@router.post(
    "/videos",
    response_model=SubmitVideoResponse,
    dependencies=[Depends(_submit_limit), Depends(llm_creds)],
)
async def submit_video(body: SubmitVideoRequest, db: AsyncSession = Depends(get_db)) -> SubmitVideoResponse:
    youtube_id = extract_youtube_id(body.url)
    if not youtube_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    existing = (
        await db.execute(
            select(Video)
            .where(Video.youtube_id == youtube_id)
            .options(
                selectinload(Video.transcript),
                selectinload(Video.sections),
                selectinload(Video.doc_summary),
            )
        )
    ).scalar_one_or_none()

    if existing and existing.status == VideoStatus.ready and not body.force_reprocess:
        if not is_stale_document(existing):
            return SubmitVideoResponse(
                video_id=existing.id,
                job_id=None,
                cached=True,
                status=existing.status.value,
            )

    if existing and existing.status == VideoStatus.ready and body.force_reprocess:
        require_llm_creds()
        existing.status = VideoStatus.queued
        video = existing
        job = Job(video_id=video.id, state=JobState.queued)
        db.add(job)
        await db.commit()
        await db.refresh(video)
        await db.refresh(job)
        await _enqueue_process(video.id)
        return SubmitVideoResponse(
            video_id=video.id,
            job_id=job.id,
            cached=False,
            status=video.status.value,
        )

    if existing and existing.status in (VideoStatus.queued, VideoStatus.processing):
        active_job = (
            await db.execute(
                select(Job)
                .where(
                    Job.video_id == existing.id,
                    Job.state.in_([JobState.queued, JobState.processing]),
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return SubmitVideoResponse(
            video_id=existing.id,
            job_id=active_job.id if active_job else None,
            cached=False,
            status=existing.status.value,
        )

    require_llm_creds()
    if existing:
        # Retry failed / no_captions
        existing.status = VideoStatus.queued
        video = existing
    else:
        video = Video(youtube_id=youtube_id, status=VideoStatus.queued)
        db.add(video)
        await db.flush()

    job = Job(video_id=video.id, state=JobState.queued)
    db.add(job)
    await db.commit()
    await db.refresh(video)
    await db.refresh(job)

    await _enqueue_process(video.id)

    return SubmitVideoResponse(
        video_id=video.id,
        job_id=job.id,
        cached=False,
        status=video.status.value,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, db: AsyncSession = Depends(get_db)) -> JobResponse:
    job = (
        await db.execute(
            select(Job).where(Job.id == job_id).options(selectinload(Job.video))
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(
        id=job.id,
        video_id=job.video_id,
        state=job.state.value,
        error=job.error,
        progress=job.progress,
        video_status=job.video.status.value,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post(
    "/videos/{video_id}/ask",
    response_model=AskResponse,
    dependencies=[Depends(_ask_limit), Depends(llm_creds)],
)
async def ask_video(video_id: UUID, body: AskRequest, db: AsyncSession = Depends(get_db)) -> AskResponse:
    require_llm_creds()

    video = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != VideoStatus.ready:
        raise HTTPException(status_code=409, detail="Document is not ready yet")

    try:
        result = await answer_question(
            db, video, body.question, history=[t.model_dump() for t in body.history]
        )
    except FAILOVER_ERRORS as exc:
        raise HTTPException(
            status_code=503,
            detail="The AI providers are busy right now — try again in ~30 seconds.",
        ) from exc
    return AskResponse(**result)


@router.post(
    "/videos/{video_id}/practice",
    response_model=PracticeResponse,
    dependencies=[Depends(_practice_limit), Depends(llm_creds)],
)
async def practice(video_id: UUID, body: PracticeRequest, db: AsyncSession = Depends(get_db)) -> PracticeResponse:
    """Generate flashcards or a quiz on demand; cached in the doc after the first call."""
    video = (
        await db.execute(
            select(Video).where(Video.id == video_id).options(selectinload(Video.doc_summary))
        )
    ).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != VideoStatus.ready or not video.doc_summary:
        raise HTTPException(status_code=409, detail="Document is not ready yet")

    content = dict(video.doc_summary.content or {})
    if content.get(body.kind):
        cached = content[body.kind]
        return PracticeResponse(
            kind=body.kind,
            cards=cached if body.kind == "flashcards" else [],
            questions=cached if body.kind == "quiz" else [],
            cached=True,
        )

    require_llm_creds()
    try:
        if body.kind == "flashcards":
            items = await generate_flashcards(db, video)
        else:
            items = await generate_quiz(db, video)
    except FAILOVER_ERRORS as exc:
        raise HTTPException(
            status_code=503,
            detail="The AI providers are busy right now — try again in ~30 seconds.",
        ) from exc
    if not items:
        raise HTTPException(status_code=502, detail="Generation came back empty — try again.")

    content[body.kind] = items
    video.doc_summary.content = content
    await db.commit()
    return PracticeResponse(
        kind=body.kind,
        cards=items if body.kind == "flashcards" else [],
        questions=items if body.kind == "quiz" else [],
        cached=False,
    )


@router.get("/videos/{video_id}", response_model=VideoDocumentResponse)
async def get_video(video_id: UUID, db: AsyncSession = Depends(get_db)) -> VideoDocumentResponse:
    video = (
        await db.execute(
            select(Video)
            .where(Video.id == video_id)
            .options(
                selectinload(Video.transcript),
                selectinload(Video.sections),
                selectinload(Video.doc_summary),
                selectinload(Video.term_occurrences).selectinload(TermOccurrence.glossary_term),
            )
        )
    ).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Surface the active job's pipeline stage so the doc page can show live progress,
    # and the failure/rejection reason so the UI can explain what happened.
    progress: str | None = None
    status_reason: str | None = None
    if video.status in (VideoStatus.queued, VideoStatus.processing):
        progress = (
            await db.execute(
                select(Job.progress)
                .where(Job.video_id == video.id)
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    elif video.status in (VideoStatus.rejected, VideoStatus.failed, VideoStatus.no_captions):
        status_reason = (
            await db.execute(
                select(Job.error)
                .where(Job.video_id == video.id)
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    elif video.status == VideoStatus.ready:
        # Rebuild failed but the worker kept the cached doc at ready — surface why.
        status_reason = (
            await db.execute(
                select(Job.error)
                .where(Job.video_id == video.id, Job.state == JobState.failed)
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    raw = video.transcript.raw_segments if video.transcript else []
    cleaned = video.transcript.cleaned_segments if video.transcript and video.transcript.cleaned_segments else raw

    glossary_by_id: dict[UUID, GlossaryTerm] = {}
    for occ in video.term_occurrences:
        if occ.glossary_term:
            glossary_by_id[occ.term_id] = occ.glossary_term

    return VideoDocumentResponse(
        id=video.id,
        youtube_id=video.youtube_id,
        title=video.title,
        channel=video.channel,
        duration_s=video.duration_s,
        lang=video.lang,
        status=video.status.value,
        progress=progress,
        status_reason=status_reason,
        tldr=video.doc_summary.tldr if video.doc_summary else None,
        overview=video.doc_summary.content if video.doc_summary else None,
        sections=[
            {
                "id": s.id,
                "idx": s.idx,
                "title": s.title,
                "start_s": s.start_s,
                "end_s": s.end_s,
                "summary_short": s.summary_short,
                "summary_full": s.summary_full,
                "content": s.content,
            }
            for s in sorted(video.sections, key=lambda x: x.idx)
        ],
        raw_segments=raw,
        cleaned_segments=cleaned,
        glossary=[
            {
                "id": term.id,
                "term": term.term,
                "display": term.display,
                "definition_beginner": term.definition_beginner,
                "domain": term.domain,
            }
            for term in sorted(glossary_by_id.values(), key=lambda t: t.display.lower())
        ],
        term_occurrences=[
            {
                "term_id": occ.term_id,
                "section_id": occ.section_id,
                "segment_idx": occ.segment_idx,
            }
            for occ in video.term_occurrences
        ],
    )


def _showcase_row(video: Video) -> ShowcaseVideoSchema:
    return ShowcaseVideoSchema(
        id=video.id,
        youtube_id=video.youtube_id,
        title=video.title,
        channel=video.channel,
        duration_s=video.duration_s,
    )


async def _load_showcase_videos(db: AsyncSession) -> list[Video]:
    settings = get_settings()
    curated = settings.showcase_id_list
    if curated:
        try:
            ids = [UUID(v) for v in curated]
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="Invalid SHOWCASE_VIDEO_IDS") from exc
        rows = (
            await db.execute(
                select(Video)
                .where(Video.id.in_(ids), Video.status == VideoStatus.ready)
            )
        ).scalars().all()
        by_id = {v.id: v for v in rows}
        return [by_id[i] for i in ids if i in by_id]

    return list(
        (
            await db.execute(
                select(Video)
                .where(Video.status == VideoStatus.ready)
                .order_by(Video.processed_at.desc().nullslast(), Video.created_at.desc())
                .limit(6)
            )
        ).scalars().all()
    )


@router.get("/showcase", response_model=list[ShowcaseVideoSchema])
async def list_showcase(db: AsyncSession = Depends(get_db)) -> list[ShowcaseVideoSchema]:
    """Ready-made study docs for the homepage — no API key required."""
    videos = await _load_showcase_videos(db)
    return [_showcase_row(v) for v in videos]


@router.get("/admin/stats", response_model=AdminStatsResponse)
async def admin_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    require_admin(request)
    status_counts = dict(
        (await db.execute(select(Video.status, func.count()).group_by(Video.status))).all()
    )
    job_counts = dict(
        (await db.execute(select(Job.state, func.count()).group_by(Job.state))).all()
    )
    llm_calls, llm_tokens = await get_llm_usage()
    recent = await _load_showcase_videos(db)
    return AdminStatsResponse(
        videos_total=sum(status_counts.values()),
        videos_ready=status_counts.get(VideoStatus.ready, 0),
        videos_processing=status_counts.get(VideoStatus.processing, 0)
        + status_counts.get(VideoStatus.queued, 0),
        videos_failed=status_counts.get(VideoStatus.failed, 0)
        + status_counts.get(VideoStatus.rejected, 0)
        + status_counts.get(VideoStatus.no_captions, 0),
        jobs_completed=job_counts.get(JobState.completed, 0),
        jobs_failed=job_counts.get(JobState.failed, 0),
        llm_calls=llm_calls,
        llm_tokens=llm_tokens,
        recent_videos=[_showcase_row(v) for v in recent[:10]],
    )
