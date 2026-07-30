# Gloss

Turn YouTube lectures and tutorials into **learnable** study documents — sectioned notes, a beginner glossary for jargon, timestamp jumps, and an embedded player. Captions only (no video download).

See `PLAN.md` for product vision and constraints.

## Stack

- **Frontend:** Next.js 15, Tailwind
- **API:** FastAPI (async SQLAlchemy)
- **Worker:** arq + Redis
- **Database:** PostgreSQL + pgvector

## Quick start

### 1. Environment

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env` for LLM summaries. Without it, the worker falls back to raw transcript text.

### 2. Start infrastructure + backend

```bash
docker compose up -d db redis
docker compose up --build api worker
```

In another terminal, run migrations (first time only):

```bash
docker compose exec api alembic upgrade head
```

Or locally if you have Python deps installed:

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
# separate terminal:
arq app.worker.settings.WorkerSettings
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). API defaults to [http://localhost:8000](http://localhost:8000).

## Docker images

Build the API and worker images from `backend/` (multi-stage Dockerfile):

```bash
docker build -t gloss-api:latest --target api ./backend
docker build -t gloss-worker:latest --target worker ./backend
```

Run the full stack with production images (no bind-mounts, no reload):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec api alembic upgrade head
```

Push to a registry (replace with your registry path):

```bash
docker tag gloss-api:latest ghcr.io/<you>/gloss-api:latest
docker tag gloss-worker:latest ghcr.io/<you>/gloss-worker:latest
docker push ghcr.io/<you>/gloss-api:latest
docker push ghcr.io/<you>/gloss-worker:latest
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/videos` | Submit `{ "url": "..." }` — returns `video_id`, `job_id`, `cached` |
| GET | `/api/jobs/{id}` | Job status |
| GET | `/api/videos/{id}` | Full study document |
| GET | `/health` | Health check |

## Phase 1 scope

- URL in → background processing → cached document out
- Caption fetch via `youtube-transcript-api`
- YouTube chapter sections (or single section fallback)
- Section summaries + TL;DR
- Frontend: submit URL, poll job, render doc with timestamp jumps + embedded player

**Phase 2** adds the auto-glossary wedge (the core differentiator).

## Open decisions

- LLM provider per task (currently OpenAI `gpt-4o-mini`)
- Auth / rate limiting for public hosting
- Polling vs SSE for job status
- Production caption fetch proxy for datacenter IPs
