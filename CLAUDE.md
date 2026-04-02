# VERA — Verification-first OCR Platform

Upload scanned receipts/invoices, OCR extracts text, user reviews and corrects low-confidence tokens, validates, then exports. AI summaries optional via Ollama.

**Version:** v1.5.0

## Build & Run

```bash
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

## Test

```bash
# Backend
cd backend && pytest --tb=short

# Frontend
cd frontend && npm test
```

## Lint

```bash
python3 -m ruff check backend/app/ backend/tests/
python3 -m ruff format --check backend/app/ backend/tests/
```

## Project Structure

```
vera/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app
│   │   ├── config/        # pydantic-settings
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # PaddleOCR, business logic
│   │   ├── api/           # route handlers
│   │   └── worker.py      # Celery worker entry
│   ├── alembic/           # database migrations
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── app/               # Next.js app router
│   ├── components/        # React components
│   ├── package.json
│   └── vitest.config.ts
├── docker-compose.yml     # 7 services
├── cliff.toml
└── CHANGELOG.md
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| backend (FastAPI) | :4000 | REST API |
| frontend (Next.js) | :3000 | Web UI |
| worker (Celery) | — | Async OCR + summaries |
| beat (Celery Beat) | — | Stuck-task recovery scheduler |
| postgres | :5432 | Primary database |
| redis | :6379 | Celery broker + sessions |
| backup | — | Scheduled pg_dump backups |

## Architecture Notes

- **Document lifecycle:** `uploaded → ocr_done → review_in_progress → validated → summarized → exported`
- **Validation is a hard gate** — summaries and exports only unlock after explicit human review
- **Celery worker** runs OCR (PaddleOCR) and AI summaries in background tasks
- **Auth:** all authentication delegated to Hub (required) — no local auth fallback
- **Alembic** manages PostgreSQL schema — always run migrations after pulling
- **License enforcement:** middleware checks Hub's `enforcement_level` hourly. Soft mode blocks uploads (402). Hard mode blocks all except `/health`, auth endpoints, and static files. Frontend can check `GET /api/license/status`. See `services/auth.py`.

## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `CELERY_BROKER_URL` | — | Redis broker URL |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.1` | Model for summaries |
| `MAX_UPLOAD_MB` | `25` | Max upload file size |
| `RETENTION_DAYS` | `30` | Document retention period |
| `HUB_BASE_URL` | — | **Required.** Hub URL for auth |
| `HUB_AUTH_API_KEY` | — | **Required.** Hub API key |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `SECURE_COOKIES` | `true` | Session cookie Secure flag |

## Things to Watch Out For

- Always run `alembic upgrade head` after pulling — migrations may have been added
- Backend is Python 3.10+ (not 3.11+ like other suite repos)
- 7 Docker services — check all are healthy with `docker compose ps`
- Stuck documents can occur if worker crashes mid-OCR — Beat task recovers these
- Frontend and backend are separate projects with separate dependency management
