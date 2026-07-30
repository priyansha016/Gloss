from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import async_session_factory
from app.models import DocSummary, GlossaryTerm, Job, JobState, Section, TermOccurrence, Transcript, Video, VideoStatus
from app.services.captions import (
    NoCaptionsError,
    build_sections_from_chapters,
    build_youtube_http_client,
    fetch_captions,
    fetch_watch_page,
    parse_chapters,
    parse_video_metadata,
    segments_for_range,
    segments_to_text,
)
from app.services.cleanup import cleanup_segments
from app.services.gatekeeper import check_video_suitability
from app.services.glossary import detect_jargon, is_term_relevant_in_section, upsert_glossary_term
from app.services.llm import (
    build_document_overview,
    build_video_outline,
    generate_doc_extras,
    generate_sections,
    key_points_to_text,
    nav_to_tldr_text,
)
from app.services.llm_context import LlmCreds, set_llm_creds
from app.services.verifier import verify_overview, verify_sections
from app.services.visuals import add_visuals


async def _set_progress(job_id: UUID | None, text: str) -> None:
    """Write the current pipeline stage to the job row.

    Uses its own short-lived session: the main pipeline session holds one big
    transaction until the end, and committing it mid-flight would persist a
    half-built document.
    """
    if not job_id:
        return
    try:
        async with async_session_factory() as session:
            job = await session.get(Job, job_id)
            if job:
                job.progress = text
                await session.commit()
    except Exception:
        pass  # progress is cosmetic — never fail the pipeline over it


async def _record_failure(session, uid: UUID, job_id: UUID | None, status: VideoStatus, error: str) -> None:
    """Roll back the in-flight build (preserving the previous doc), then mark the failure.

    Committing without the rollback would persist the mid-transaction wipe/partial
    inserts — exactly the 'failed reprocess destroys the cached doc' bug.
    """
    await session.rollback()
    video = await session.get(Video, uid)
    if video:
        video.status = status
    if job_id:
        job = await session.get(Job, job_id)
        if job:
            job.state = JobState.failed
            job.error = error
    await session.commit()


async def process_video(ctx: dict, video_id: str, llm_creds: dict | None = None) -> None:
    """Background job: captions → glossary → cleanup → sections → summaries.

    `llm_creds` carries the submitter's own API key (bring-your-own-key). Setting
    it here, before any stage runs, is enough: the pipeline's parallel stages copy
    this context when they spawn. Default None = use the server's configured key.
    """
    set_llm_creds(LlmCreds.from_dict(llm_creds))
    uid = UUID(video_id)
    settings = get_settings()
    async with async_session_factory() as session:
        video = await session.get(Video, uid)
        if not video:
            return

        job = (
            await session.execute(
                select(Job)
                .where(Job.video_id == uid, Job.state == JobState.queued)
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if job:
            job.state = JobState.processing
        video.status = VideoStatus.processing
        await session.commit()

        job_id = job.id if job else None

        try:
            await _set_progress(job_id, "Fetching captions & video info…")
            async with build_youtube_http_client() as client:
                watch_html = await fetch_watch_page(video.youtube_id, client=client)
                metadata = parse_video_metadata(watch_html)
                video.title = metadata.title
                video.channel = metadata.channel
                video.duration_s = metadata.duration_s

                segments, lang = await fetch_captions(video.youtube_id)
                video.lang = lang
                raw = [s.to_dict() for s in segments]
                full_text = segments_to_text(segments)

                # Gatekeeper: Gloss only processes teaching content. Reject music /
                # Q&A compilations / entertainment BEFORE spending tokens on them.
                await _set_progress(job_id, "Checking this is a tutorial or lecture…")
                verdict = await check_video_suitability(
                    metadata.title, metadata.channel, metadata.duration_s, segments, full_text
                )
                if not verdict.suitable:
                    had_doc = (
                        await session.execute(
                            select(DocSummary.id).where(DocSummary.video_id == uid).limit(1)
                        )
                    ).scalar_one_or_none() is not None
                    if had_doc:
                        # Rebuild rejection: roll back and keep the cached doc visible.
                        await _record_failure(session, uid, job_id, VideoStatus.ready, verdict.reason)
                    else:
                        video.status = VideoStatus.rejected
                        if job:
                            job.state = JobState.failed
                            job.error = verdict.reason
                        await session.commit()
                    return

                chapters = parse_chapters(watch_html)
                section_defs = build_sections_from_chapters(chapters, metadata.duration_s)
                chapter_titles = [s["title"] for s in section_defs]

                await _set_progress(job_id, "Building the beginner glossary…")
                jargon_terms = await detect_jargon(
                    full_text,
                    video.title,
                    chapter_titles=chapter_titles,
                )
                glossary_rows: list[GlossaryTerm] = []
                for jargon in jargon_terms:
                    glossary_rows.append(await upsert_glossary_term(session, jargon))
                known_terms = [g.display for g in glossary_rows]

                cleaned = await cleanup_segments(segments, known_terms)
                cleaned_raw = [s.to_dict() for s in cleaned]

                # Atomic swap: wipe the old doc INSIDE this transaction, right before the
                # new inserts. If anything fails later (rate limit, timeout), the rollback
                # restores the previous doc instead of leaving an empty failed video.
                await session.execute(delete(TermOccurrence).where(TermOccurrence.video_id == uid))
                await session.execute(delete(Section).where(Section.video_id == uid))
                await session.execute(delete(DocSummary).where(DocSummary.video_id == uid))
                await session.execute(delete(Transcript).where(Transcript.video_id == uid))

                transcript = Transcript(
                    video_id=video.id,
                    raw_segments=raw,
                    cleaned_segments=cleaned_raw,
                )
                session.add(transcript)
                await session.flush()

                section_inputs: list[tuple[str, str]] = []
                for sec_def in section_defs:
                    range_segments = segments_for_range(cleaned, sec_def["start_s"], sec_def["end_s"])
                    text = segments_to_text(range_segments)
                    section_inputs.append((sec_def["title"], text or "(no transcript in range)"))

                # Pass 1: whole-video outline (roles that connect sections). Pass 2: each
                # section's structured notes, primed with its neighbours' roles.
                await _set_progress(job_id, "Outlining the video…")
                outline = await build_video_outline(video.title, section_defs, section_inputs)
                await _set_progress(job_id, f"Writing notes for {len(section_defs)} sections…")
                section_contents = await generate_sections(
                    video.title, outline, section_defs, section_inputs
                )

                # Verifier: critique + targeted repairs before anything is stored.
                section_quality: dict = {"fixed": [], "unresolved": []}
                if settings.enable_verifier:
                    await _set_progress(job_id, "Verifying quality & repairing weak spots…")
                    section_contents, section_quality = await verify_sections(
                        video.title, outline, section_defs, section_inputs, section_contents
                    )

                # Visual designer: purpose-built illustrations for mechanism-heavy sections.
                if settings.enable_visuals:
                    await _set_progress(job_id, "Designing visuals for complex sections…")
                    section_contents, visual_notes = await add_visuals(
                        video.title, section_defs, section_inputs, section_contents
                    )
                    section_quality["unresolved"].extend(visual_notes)

                section_summaries: list[tuple[str, str]] = []
                section_rows: list[Section] = []
                section_summary_by_idx: dict[int, tuple[str, str]] = {}
                headlines: list[str] = []
                for sec_def, content in zip(section_defs, section_contents, strict=True):
                    short = content["headline"]
                    full = key_points_to_text(content["key_points"])
                    headlines.append(short)
                    section_summaries.append((sec_def["title"], short))
                    section_summary_by_idx[sec_def["idx"]] = (short, full)
                    section = Section(
                        video_id=video.id,
                        idx=sec_def["idx"],
                        title=sec_def["title"],
                        start_s=sec_def["start_s"],
                        end_s=sec_def["end_s"],
                        summary_short=short,
                        summary_full=full,
                        content=content,
                    )
                    session.add(section)
                    section_rows.append(section)

                await session.flush()

                for glossary in glossary_rows:
                    for section in section_rows:
                        range_segments = segments_for_range(cleaned, section.start_s, section.end_s)
                        section_text = segments_to_text(range_segments)
                        short, full = section_summary_by_idx.get(section.idx, ("", ""))
                        section_summary = " ".join(x for x in (short, full) if x)
                        if not is_term_relevant_in_section(
                            glossary.display,
                            section_title=section.title,
                            section_summary=section_summary,
                            section_text=section_text,
                        ):
                            continue
                        global_idx = 0
                        for seg in cleaned:
                            if section.start_s <= seg.start_s < section.end_s:
                                if glossary.display.lower() in seg.text.lower():
                                    session.add(
                                        TermOccurrence(
                                            video_id=video.id,
                                            term_id=glossary.id,
                                            section_id=section.id,
                                            segment_idx=global_idx,
                                        )
                                    )
                            global_idx += 1

                await _set_progress(job_id, "Generating summary, notes & Q&A…")
                extras = await generate_doc_extras(
                    video.title,
                    outline.get("teaches", ""),
                    section_defs,
                    section_contents,
                    full_text,
                )

                overview_quality: dict = {"fixed": [], "unresolved": []}
                if settings.enable_verifier:
                    await _set_progress(job_id, "Final quality check…")
                    outline, extras, overview_quality = await verify_overview(
                        video.title, outline, section_defs, section_inputs,
                        section_contents, extras, full_text,
                    )
                overview = {
                    **build_document_overview(outline, section_defs, headlines),
                    **extras,
                    "quality": {
                        "fixed": section_quality["fixed"] + overview_quality["fixed"],
                        "unresolved": section_quality["unresolved"] + overview_quality["unresolved"],
                    },
                }
                session.add(
                    DocSummary(
                        video_id=video.id,
                        tldr=nav_to_tldr_text(overview["nav"]),
                        content=overview,
                    )
                )

                video.status = VideoStatus.ready
                video.processed_at = datetime.now(UTC)
                if job:
                    job.state = JobState.completed
                await session.commit()

        except NoCaptionsError as exc:
            await _record_failure(session, uid, job_id, VideoStatus.no_captions, str(exc))

        except Exception as exc:
            await _record_failure(session, uid, job_id, VideoStatus.failed, str(exc))
            raise
