# Design Log #001 — Phase 1 End-to-End Skeleton

## Background

YouTube Skim converts lecture/tutorial URLs into interactive study documents. Phase 1 delivers URL-in → document-out without the glossary wedge (Phase 2).

See `PLAN.md` for full product context and constraints.

## Problem

Need a working loop: submit URL, background processing, cached results, render doc with timestamps and embedded player.

## Questions and Answers

**Q: LLM provider for Phase 1 summaries?**  
A: OpenAI (`gpt-4o-mini`) via env var — swappable later. Requires `OPENAI_API_KEY`.

**Q: Job status transport?**  
A: Simple polling (frontend polls every 2s). SSE deferred.

**Q: Auth?**  
A: None in Phase 1. Rate limiting deferred.

**Q: Worker framework?**  
A: `arq` (async-native, pairs well with FastAPI).

**Q: Chapter detection without yt-dlp?**  
A: Parse `ytInitialPlayerResponse` from watch page for macro markers; fallback to single section.

## Design

```
POST /api/videos { url } → cache hit | enqueue job
GET  /api/jobs/{id}      → queued | processing | ready | failed | no_captions
GET  /api/videos/{id}    → full document
```

Monorepo: `backend/` (FastAPI + arq), `frontend/` (Next.js), `docker-compose.yml` (Postgres+pgvector, Redis, API, worker).

## Implementation Plan

1. Docker Compose + env template
2. SQLAlchemy models + Alembic initial migration
3. Caption fetch (`youtube-transcript-api`) + chapter parser
4. OpenAI section summaries + TL;DR
5. API routes + arq worker
6. Next.js: home (URL form), doc page (sections, player, timestamp links)

## Trade-offs

- `create_all` skipped in favor of Alembic for reproducible schema
- Glossary/RAG tables omitted until Phase 2
- Chapter parsing is best-effort; single-section fallback is acceptable

## Implementation Results

- Backend scaffold complete: FastAPI, SQLAlchemy models, Alembic migration, arq worker
- Frontend scaffold complete: Next.js home + doc pages, polling, YouTube embed
- Fixed `youtube-transcript-api` v1.x API (`fetch`/`list` instance methods)
- Verification: frontend `npm run build` passes; backend imports pass
- Docker smoke test not run in agent environment (Docker socket unavailable)

### Deviations

- Frontend created manually instead of `create-next-app` (sandbox/interrupt issues)
- shadcn/ui deferred — plain Tailwind components for Phase 1 speed
