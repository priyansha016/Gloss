# Design Log #002 — Pre-Hosting Hardening (Tier 1)

## Background

Gloss is functionally complete (gatekeeper → glossary → sections → verifier → visuals → doc extras, plus Ask & Practice). Next step is a public, free deploy (Cloudflare Pages frontend + Oracle Always-Free VM backend, joined by a Cloudflare Tunnel). Before exposing a public URL, three gaps must be closed.

## Problem

1. **No abuse protection.** `POST /api/videos` (processing), `/ask`, and `/practice` each spend LLM tokens. A public URL with no cap can drain the free Groq/Gemini quota in minutes, or be used as a free LLM proxy.
2. **`FAST_PROCESSING` no longer means "fast".** It still shrinks the glossary (`glossary.py`) and skips cleanup (`cleanup.py`), but the expensive verifier + visuals + doc-extras stages run unconditionally. The flag misrepresents cost.
3. **Stale config/docs.** `config.py` defaults to `gpt-4o-mini`; `.env.example` leads with a Gemma profile. Neither reflects the real Groq-primary + Gemini-failover setup.

## Questions and Answers

**Q: Rate-limit library or custom?**
A: Custom Redis fixed-window. Redis is already in the stack (arq); no new dependency; works across processes; simple to reason about.

**Q: Fail-open or fail-closed if Redis is down?**
A: Fail-open. This is a small free app; availability matters more than perfect enforcement, and the worker/queue already needs Redis (so a Redis outage means processing is down anyway). Log on failure.

**Q: How is the client identified behind the Cloudflare Tunnel?**
A: Prefer `CF-Connecting-IP`, then first hop of `X-Forwarded-For`, then `request.client.host`.

**Q: Repurpose `FAST_PROCESSING` or add flags?**
A: Add explicit `ENABLE_VERIFIER` / `ENABLE_VISUALS` (default true). Keep `FAST_PROCESSING` for its real, existing role (glossary size + cleanup skip) and document that scope. This removes the "flag lies" problem without changing current behavior by default.

**Q: What limits?**
A: Per-IP fixed window (defaults, env-overridable):
- submit: 15 / hour (each is minutes of LLM work)
- ask: 40 / hour
- practice: 20 / hour
Global `RATE_LIMIT_ENABLED` (default true; set false for local dev).

## Design

```
app/services/ratelimit.py
  get_redis()                         # lazy shared redis.asyncio client (fail-open)
  _client_ip(request)                 # CF-Connecting-IP → XFF → client.host
  enforce(request, bucket, limit, window_s)  # INCR+EXPIRE fixed window → 429 on exceed
  RateLimit(bucket, limit, window)    # FastAPI dependency factory
```

Applied as route dependencies:
- `POST /api/videos`  → submit bucket
- `POST /api/videos/{id}/ask` → ask bucket
- `POST /api/videos/{id}/practice` → practice bucket

429 response includes a `Retry-After` header (seconds to window reset).

Worker: wrap `verify_sections`/`verify_overview` in `if settings.enable_verifier` and `add_visuals` in `if settings.enable_visuals`.

## Implementation Plan

1. `ratelimit.py` service.
2. `config.py`: `rate_limit_enabled`, `rate_limit_submit_per_hour`, `rate_limit_ask_per_hour`, `rate_limit_practice_per_hour`, `enable_verifier`, `enable_visuals`.
3. Wire dependencies into the three POST routes.
4. Gate verifier/visuals in the worker.
5. Refresh `.env.example` (real profiles + new knobs) and `config.py` defaults.
6. Add tests for the limiter window logic; run the suite.

## Trade-offs

- Fixed window (not sliding/token-bucket) can allow a 2× burst at a window boundary. Acceptable for abuse protection at this scale; simpler and cheaper than a sliding log.
- Fail-open means a Redis outage disables limits — acceptable given Redis is already critical-path for processing.
- IP-based limiting is coarse (shared NATs, VPNs) but needs no auth. Auth/BYOK is a later phase.

## Implementation Results

Implemented as designed. Files:
- `backend/app/services/ratelimit.py` — new. Redis fixed-window limiter, `_client_ip`, `enforce`, `RateLimit` dependency. Fail-open.
- `backend/app/config.py` — added `enable_verifier`, `enable_visuals`, `rate_limit_enabled`, `rate_limit_{submit,ask,practice}_per_hour`; documented `fast_processing`'s real (cheap-knobs-only) scope.
- `backend/app/api/routes.py` — attached `RateLimit` deps to `POST /videos`, `/ask`, `/practice`.
- `backend/app/worker/tasks.py` — gated `verify_sections`/`verify_overview` behind `enable_verifier`, `add_visuals` behind `enable_visuals`; quality report defaults preserved when skipped.
- `.env.example` — rewritten: Groq+Gemini failover as the lead profile, documented all new knobs.
- `backend/tests/test_ratelimit.py` — new, 7 tests.

Tests: **83/83 passing** (was 76; +7 for the limiter). App import smoke test OK.

### Deviations from design

- None functionally. Limits are resolved from settings at router import time (module-level `RateLimit` instances); `enforce` still re-reads `rate_limit_enabled` at call time, so the enable/disable toggle is dynamic even though the numeric limits are fixed at boot (fine for a deployed process).

### Notes for deploy

- Behind the Cloudflare Tunnel the real client IP arrives as `CF-Connecting-IP` (handled). If ever fronted by a different proxy, confirm the header or limits collapse to one bucket.
- `RATE_LIMIT_ENABLED=false` recommended in local `.env` to avoid friction while developing.
