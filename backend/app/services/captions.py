import asyncio
import json
import re
from dataclasses import dataclass

import httpx
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)
from youtube_transcript_api.proxies import GenericProxyConfig, ProxyConfig

from app.config import get_settings

PLAYER_RESPONSE_RE = re.compile(r"ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;\s*(?:var\s|<)")
YT_INITIAL_DATA_RE = re.compile(r"var ytInitialData = (\{.*?\});")
DESCRIPTION_LINE_RE = re.compile(r"^(\d{1,2}:)?(\d{1,2}):(\d{2})\s*[-–—]?\s*(.+)$")

YOUTUBE_HTTP_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


@dataclass
class CaptionSegment:
    start_s: float
    end_s: float
    text: str

    def to_dict(self) -> dict:
        return {"start_s": self.start_s, "end_s": self.end_s, "text": self.text}


@dataclass
class Chapter:
    title: str
    start_s: float


@dataclass
class VideoMetadata:
    title: str | None
    channel: str | None
    duration_s: int | None


class CaptionFetchError(Exception):
    pass


class NoCaptionsError(CaptionFetchError):
    pass


def _proxy_config() -> ProxyConfig | None:
    """Build a proxy config for youtube-transcript-api from settings (None = direct)."""
    url = get_settings().youtube_proxy_url.strip()
    if not url:
        return None
    return GenericProxyConfig(http_url=url, https_url=url)


def build_youtube_http_client() -> httpx.AsyncClient:
    """httpx client for YouTube watch-page requests, routed through the proxy if set."""
    proxy = get_settings().youtube_proxy_url.strip() or None
    return httpx.AsyncClient(headers=YOUTUBE_HTTP_HEADERS, proxy=proxy, timeout=30.0)


def _segments_from_transcript(items: list[dict]) -> list[CaptionSegment]:
    segments: list[CaptionSegment] = []
    for item in items:
        start = float(item["start"])
        duration = float(item.get("duration", 0))
        text = item.get("text", "").strip()
        if not text:
            continue
        segments.append(CaptionSegment(start_s=start, end_s=start + duration, text=text))
    return segments


def _fetch_captions_sync(youtube_id: str) -> tuple[list[dict], str | None]:
    """Blocking caption fetch (youtube-transcript-api uses `requests`)."""
    api = YouTubeTranscriptApi(proxy_config=_proxy_config())
    try:
        fetched = api.fetch(youtube_id, languages=["en", "en-US", "en-GB"])
        return fetched.to_raw_data(), fetched.language_code
    except TranscriptsDisabled as exc:
        raise NoCaptionsError("Captions are disabled for this video") from exc
    except NoTranscriptFound:
        try:
            transcript_list = api.list(youtube_id)
            available = [t.language_code for t in transcript_list]
            if not available:
                raise NoCaptionsError("No caption track available")
            transcript = transcript_list.find_transcript(available)
            fetched = transcript.fetch()
            return fetched.to_raw_data(), transcript.language_code
        except NoCaptionsError:
            raise
        except Exception as exc:
            raise NoCaptionsError("No caption track available") from exc


async def fetch_captions(youtube_id: str) -> tuple[list[CaptionSegment], str | None]:
    """Fetch caption track via youtube-transcript-api (no media download).

    Requests go through the configured proxy (YOUTUBE_PROXY_URL) so this works from
    datacenter IPs in production, where YouTube blocks direct caption requests.

    The library is synchronous (`requests`), so run it in a thread to avoid blocking
    the worker's event loop (and every other concurrent job) during the HTTP round-trip.
    """
    items, lang = await asyncio.to_thread(_fetch_captions_sync, youtube_id)
    return _segments_from_transcript(items), lang


async def fetch_watch_page(youtube_id: str, *, client: httpx.AsyncClient) -> str:
    """Fetch the watch-page HTML once; metadata and chapters are both parsed from it."""
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    return response.text


def parse_video_metadata(html: str) -> VideoMetadata:
    match = PLAYER_RESPONSE_RE.search(html)
    if not match:
        return VideoMetadata(title=None, channel=None, duration_s=None)

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return VideoMetadata(title=None, channel=None, duration_s=None)

    video_details = data.get("videoDetails") or {}
    title = video_details.get("title")
    channel = video_details.get("author")
    duration_s = int(video_details.get("lengthSeconds") or 0) or None

    return VideoMetadata(title=title, channel=channel, duration_s=duration_s)


def parse_chapters_from_player_response(html: str, duration_s: int | None) -> list[Chapter]:
    match = PLAYER_RESPONSE_RE.search(html)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    chapters: list[Chapter] = []
    markers = (
        data.get("playerOverlays", {})
        .get("playerOverlayRenderer", {})
        .get("decoratedPlayerBarRenderer", {})
        .get("playerBar", {})
        .get("multiMarkersPlayerBarRenderer", {})
        .get("markersMap", [])
    )

    for marker_map in markers:
        key = marker_map.get("key")
        if key not in ("AUTO_CHAPTERS", "DESCRIPTION_CHAPTERS", "CHAPTER"):
            continue
        marker_list = (
            marker_map.get("value", {})
            .get("chaptersRenderer", {})
            .get("chapters", [])
        )
        for chapter in marker_list:
            renderer = chapter.get("chapterRenderer") or {}
            title = _chapter_title_from_renderer(renderer)
            start_ms = int(renderer.get("timeRangeStartMillis") or renderer.get("startTimeMs") or 0)
            chapters.append(Chapter(title=title, start_s=start_ms / 1000.0))

    return _sort_dedupe_chapters(chapters)


def _chapter_title_from_renderer(renderer: dict) -> str:
    title_obj = renderer.get("title") or {}
    simple = title_obj.get("simpleText") or ""
    if simple:
        return simple
    runs = title_obj.get("runs") or []
    return runs[0].get("text", "Section") if runs else "Section"


def _walk_chapter_renderers(obj) -> list[dict]:
    found: list[dict] = []
    if isinstance(obj, dict):
        if "chapterRenderer" in obj:
            found.append(obj["chapterRenderer"])
        for value in obj.values():
            found.extend(_walk_chapter_renderers(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_walk_chapter_renderers(item))
    return found


def parse_chapters_from_yt_initial_data(html: str) -> list[Chapter]:
    match = YT_INITIAL_DATA_RE.search(html)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    chapters: list[Chapter] = []
    for renderer in _walk_chapter_renderers(data):
        title = _chapter_title_from_renderer(renderer)
        start_ms = int(renderer.get("timeRangeStartMillis") or renderer.get("startTimeMs") or 0)
        chapters.append(Chapter(title=title, start_s=start_ms / 1000.0))

    return _sort_dedupe_chapters(chapters)


def _timestamp_line_to_seconds(h: str | None, m: str, s: str) -> float:
    hours = int(h.rstrip(":")) if h else 0
    return hours * 3600 + int(m) * 60 + int(s)


def parse_chapters_from_description(description: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    for line in description.splitlines():
        line = line.strip()
        match = DESCRIPTION_LINE_RE.match(line)
        if not match:
            continue
        title = match.group(4).strip()
        if not title:
            continue
        start_s = _timestamp_line_to_seconds(match.group(1), match.group(2), match.group(3))
        chapters.append(Chapter(title=title, start_s=start_s))

    return _sort_dedupe_chapters(chapters)


def _sort_dedupe_chapters(chapters: list[Chapter]) -> list[Chapter]:
    if not chapters:
        return []

    chapters.sort(key=lambda c: c.start_s)
    deduped: list[Chapter] = []
    seen_starts: set[int] = set()
    for chapter in chapters:
        start_key = int(chapter.start_s)
        if start_key in seen_starts:
            continue
        seen_starts.add(start_key)
        deduped.append(chapter)
    return deduped


def parse_chapters_from_watch_page(html: str, description: str | None = None) -> list[Chapter]:
    """Try multiple YouTube chapter sources (player JSON, page data, description)."""
    for parser in (
        lambda: parse_chapters_from_player_response(html, None),
        lambda: parse_chapters_from_yt_initial_data(html),
        lambda: parse_chapters_from_description(description or ""),
    ):
        chapters = parser()
        if chapters:
            return chapters
    return []


def _description_from_watch_page(html: str) -> str | None:
    match = PLAYER_RESPONSE_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return (data.get("videoDetails") or {}).get("shortDescription")


def parse_chapters(html: str) -> list[Chapter]:
    """Parse chapters from already-fetched watch-page HTML (player JSON, page data, description)."""
    return parse_chapters_from_watch_page(html, _description_from_watch_page(html))


def _format_mmss(seconds: float) -> str:
    total = int(max(0, seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def build_time_chunk_sections(duration_s: int | None, chunk_seconds: int = 360) -> list[dict]:
    """Fallback when YouTube provides no chapters: split by fixed time windows."""
    end = float(duration_s or 0)
    if end <= chunk_seconds:
        return [{"idx": 0, "title": "Full video", "start_s": 0.0, "end_s": end}]

    sections: list[dict] = []
    start = 0.0
    idx = 0
    while start < end - 1:
        chunk_end = min(start + chunk_seconds, end)
        sections.append(
            {
                "idx": idx,
                "title": f"{_format_mmss(start)} – {_format_mmss(chunk_end)}",
                "start_s": start,
                "end_s": chunk_end,
            }
        )
        start = chunk_end
        idx += 1
    return sections


def build_sections_from_chapters(chapters: list[Chapter], duration_s: int | None) -> list[dict]:
    if chapters:
        sections: list[dict] = []
        for i, chapter in enumerate(chapters):
            start = chapter.start_s
            end = chapters[i + 1].start_s if i + 1 < len(chapters) else float(duration_s or chapter.start_s + 60)
            sections.append(
                {
                    "idx": i,
                    "title": chapter.title,
                    "start_s": start,
                    "end_s": end,
                }
            )
        return sections

    settings = get_settings()
    chunk_seconds = max(300, settings.section_chunk_minutes * 60)
    return build_time_chunk_sections(duration_s, chunk_seconds)


def segments_for_range(segments: list[CaptionSegment], start_s: float, end_s: float) -> list[CaptionSegment]:
    return [s for s in segments if s.start_s < end_s and s.end_s > start_s]


def segments_to_text(segments: list[CaptionSegment]) -> str:
    return " ".join(s.text for s in segments)
