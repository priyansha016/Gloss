"""Request-scoped dependencies: user-supplied LLM credentials."""

import secrets

from fastapi import HTTPException, Request

from app.config import get_settings
from app.services.llm_context import build_creds, get_llm_creds, set_llm_creds

# 428 Precondition Required: the request is well-formed, but the client must
# supply a key before we'll spend tokens. Distinct from 401/403 (which the
# frontend would read as "your key is wrong") and from 402.
USER_KEY_REQUIRED_STATUS = 428


async def llm_creds(request: Request) -> None:
    """Read the key headers into the request's context.

    Runs as a dependency (same task as the handler), so every LLM call in the
    request — including ones spawned with asyncio.gather — sees the credentials.
    Never raises: reading cached documents must keep working without a key.
    """
    set_llm_creds(
        build_creds(
            request.headers.get("X-LLM-Key"),
            provider=request.headers.get("X-LLM-Provider"),
            base_url=request.headers.get("X-LLM-Base-Url"),
            model=request.headers.get("X-LLM-Model"),
        )
    )


def require_llm_creds() -> None:
    """Guard the moment before we actually spend tokens.

    Called inside handlers rather than as a dependency so cache hits (an existing
    doc, already-generated flashcards) still serve users without a key.
    """
    settings = get_settings()
    if get_llm_creds() is not None:
        return
    if settings.require_user_key:
        raise HTTPException(
            status_code=USER_KEY_REQUIRED_STATUS,
            detail="user_key_required",
        )
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="LLM is not configured")


def require_admin(request: Request) -> None:
    """Owner-only routes. Disabled when ADMIN_SECRET is unset (404, not 401)."""
    secret = get_settings().admin_secret.strip()
    if not secret:
        raise HTTPException(status_code=404, detail="Not found")
    provided = request.headers.get("X-Admin-Key", "")
    if not secrets.compare_digest(provided, secret):
        raise HTTPException(status_code=401, detail="Invalid admin key")
