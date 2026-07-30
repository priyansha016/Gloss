"""Rolling LLM usage counters in Redis (owner dashboard only)."""

import logging

from app.services.ratelimit import get_redis

logger = logging.getLogger(__name__)

_CALLS_KEY = "gloss:stats:llm_calls"
_TOKENS_KEY = "gloss:stats:llm_tokens"


async def record_llm_usage(total_tokens: int) -> None:
    if total_tokens <= 0:
        total_tokens = 0
    redis = get_redis()
    if redis is None:
        return
    try:
        pipe = redis.pipeline()
        pipe.incr(_CALLS_KEY)
        if total_tokens:
            pipe.incrby(_TOKENS_KEY, total_tokens)
        await pipe.execute()
    except Exception:
        logger.debug("usage_stats: redis increment failed", exc_info=True)


async def get_llm_usage() -> tuple[int, int]:
    redis = get_redis()
    if redis is None:
        return 0, 0
    try:
        calls, tokens = await redis.mget(_CALLS_KEY, _TOKENS_KEY)
        return int(calls or 0), int(tokens or 0)
    except Exception:
        logger.debug("usage_stats: redis read failed", exc_info=True)
        return 0, 0
