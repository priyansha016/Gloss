from app.models import Video


def is_stale_document(video: Video) -> bool:
    """Detect docs whose section summaries are raw-transcript fallbacks, not real summaries.

    Note: we deliberately do NOT inspect the TL;DR format here. Fast mode emits
    timestamped bullets while non-fast mode emits prose, so any format-based check
    would wrongly flag every cloud-processed doc as stale and reprocess it on each
    resubmit — defeating the per-video cache (PLAN §8/§10).
    """
    if not video.doc_summary or not video.sections:
        return False

    for section in video.sections:
        short = (section.summary_short or "").strip()
        if not short:
            continue
        # Raw caption fallback: long, lowercase start, reads like spoken transcript
        if len(short) > 220:
            return True
        if short[0].islower() and short.count(".") <= 1:
            return True

    return False
