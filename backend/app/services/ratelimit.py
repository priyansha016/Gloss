"""Per-IP rate limiting backed by Redis (fixed window).

Gloss will be publicly reachable, and its expensive endpoints (video processing,
Ask, Practice) each spend LLM tokens. Without a cap, a public URL can drain the
free Groq/Gemini quota in minutes or be abused as a free LLM proxy.

Design notes:
- Fixed window via INCR + EXPIRE: one counter per (bucket, ip, window). Cheap and
  multi-process safe. A boundary burst of up to 2x is acceptable at this scale.
- Fail-open: if Redis is unreachable we allow the request (and log). Redis is already
  critical-path for the job queue, so a Redis outage means processing is down anyway;
  we don't want the limiter to be a second, independent point of failure.
- Client IP resolves behind the Cloudflare Tunnel / proxy: CF-Connecting-IP first,
  then the first hop of X-Forwarded-For, then the socket peer.
"""

import logging
import time

import redis.asyncio as aioredis
from fastapi import HTTPException, Request

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis | None:
    """Lazily build a shared async Redis client. None if construction fails."""
    global _redis
    if _redis is None:
        try:
            _redis = aioredis.from_url(
                get_settings().redis_url, encoding="utf-8", decode_responses=True
            )
        except Exception:  # pragma: no cover - construction is effectively never failing
            logger.warning("Rate limiter: could not build Redis client; limiting disabled")
            return None
    return _redis


def _client_ip(request: Request) -> str:
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce(request: Request, bucket: str, limit: int, window_s: int) -> None:
    """Increment the (bucket, ip) counter for the current window; raise 429 if over.

    Fail-open on any Redis error.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled or limit <= 0:
        return

    redis = get_redis()
    if redis is None:
        return

    ip = _client_ip(request)
    window_id = int(time.time()) // window_s
    key = f"rl:{bucket}:{ip}:{window_id}"
    try:
        count = await redis.incr(key)
        if count == 1:
            # First hit in this window — set the TTL so the counter self-expires.
            await redis.expire(key, window_s)
        if count > limit:
            ttl = await redis.ttl(key)
            retry_after = ttl if ttl and ttl > 0 else window_s
            raise HTTPException(
                status_code=429,
                detail="Rate limit reached. Please wait a bit before trying again.",
                headers={"Retry-After": str(retry_after)},
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning("Rate limiter: Redis error on bucket=%s — allowing request", bucket)
        return


class RateLimit:
    """FastAPI dependency: enforce a named bucket's limit on the incoming request."""

    def __init__(self, bucket: str, limit: int, window_s: int = 3600) -> None:
        self.bucket = bucket
        self.limit = limit
        self.window_s = window_s

    async def __call__(self, request: Request) -> None:
        await enforce(request, self.bucket, self.limit, self.window_s)
