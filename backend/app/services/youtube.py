import re
from urllib.parse import parse_qs, urlparse

YOUTUBE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def extract_youtube_id(url: str) -> str | None:
    url = url.strip()
    if YOUTUBE_ID_RE.match(url):
        return url

    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")

    if host in ("youtu.be",):
        candidate = parsed.path.lstrip("/").split("/")[0]
        return candidate if YOUTUBE_ID_RE.match(candidate) else None

    if host in ("youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            vid = qs.get("v", [None])[0]
            return vid if vid and YOUTUBE_ID_RE.match(vid) else None
        if parsed.path.startswith("/embed/"):
            candidate = parsed.path.split("/")[2]
            return candidate if YOUTUBE_ID_RE.match(candidate) else None
        if parsed.path.startswith("/shorts/"):
            candidate = parsed.path.split("/")[2]
            return candidate if YOUTUBE_ID_RE.match(candidate) else None

    return None
