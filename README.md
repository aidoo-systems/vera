# VERA — Validated Extraction & Review Assistant

VERA is a verification-first OCR platform that extracts text from document images and PDFs, highlights low-confidence tokens for human review, validates corrections, and produces trustworthy summaries and structured exports. Unlike fully automated pipelines, VERA enforces a human-in-the-loop validation gate — summaries and exports only unlock after explicit review completion.

## Key Features

- **Verification-first workflow** — human review is mandatory before export, ensuring data integrity
- **Multi-page PDF support** — per-page review and export; document-level operations require all pages validated
- **Confidence-based highlighting** — high (auto-accept), medium (review suggested), low (blocks export)
- **Inline correction** — edit tokens directly on the review page with visual bounding box overlay
- **AI summaries** — optional Ollama integration for intelligent document summaries (graceful fallback to offline extraction)
- **Structured data extraction** — dates, currency amounts, invoice/order IDs, emails, phone numbers, VAT IDs
- **Self-hosted & private** — all processing runs locally via PaddleOCR; no data leaves your network

## Architecture

| Component | Technology |
|-----------|-----------|
| Frontend | Next.js (React, TypeScript) |
| Backend | FastAPI (Python) |
| OCR | PaddleOCR (local, offline) |
| Database | PostgreSQL |
| Task Queue | Celery + Redis |
| AI Summaries | Ollama (optional) |

### Service Ports

| Service | Port |
|---------|------|
| Frontend | :3000 |
| Backend API | :4000 |
| PostgreSQL | :5432 |
| Redis | :6379 |

## Document Lifecycle

```
uploaded -> processing -> ocr_done -> review_in_progress -> validated -> summarized -> exported
                                                                    \-> canceled
```

Validation is a **hard gate**. Summaries and exports are only available after explicit review completion. For multi-page PDFs, each page is reviewed independently.

## Getting Started

### Prerequisites

- Docker and Docker Compose
- [OLLAMA repo](../OLLAMA) running (optional, for AI summaries)

### Docker (Recommended)

```bash
# 1. (Optional) Start Ollama for AI summaries
cd ../OLLAMA && docker compose up -d
./scripts/pull-models.sh llama3.1
cd ../VERA

# 2. Copy and edit config
cp .env.example .env

# 3. Start VERA
docker compose up -d --build

# 4. Run database migrations
docker compose exec backend alembic upgrade head

# 5. Open the app
# Frontend: http://localhost:3000
# Backend:  http://localhost:4000
```

If your database already has tables but Alembic has never been run, stamp the baseline first:

```bash
docker compose exec backend alembic stamp 0001_create_tables
docker compose exec backend alembic upgrade head
```

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://vera:vera@localhost:5432/vera
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Worker
celery -A app.worker.celery_app worker --loglevel=info --concurrency=2

# Frontend
cd frontend
npm install
npm run dev
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://vera:vera@postgres:5432/vera` | PostgreSQL connection string |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Redis broker URL |
| `DATA_DIR` | `/data` | Upload storage directory |
| `MAX_UPLOAD_MB` | `25` | Maximum upload file size |
| `STRICT_MIME_VALIDATION` | `1` | Enforce MIME type validation |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins (comma-separated) |
| `UPLOAD_RATE_LIMIT` | `10/minute` | Rate limit for uploads |

### Ollama (AI Summaries)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://ollama:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.1` | Model for AI summaries |
| `OLLAMA_TIMEOUT` | `300` | Request timeout (seconds) |
| `OLLAMA_RETRIES` | `2` | Retry attempts |
| `SUMMARY_MAX_CHARS` | `2000` | Max summary length |

### Retention

| Variable | Default | Description |
|----------|---------|-------------|
| `RETENTION_DAYS` | `30` | Days before cleanup |
| `RETENTION_TRIGGER` | `post_export` | When to start retention (`post_export` or `post_review`) |
| `RETENTION_MODE` | `delete` | Cleanup mode (`delete` or `archive`) |
| `RETENTION_ARCHIVE_DIR` | `./archive` | Archive destination |
| `RETENTION_INTERVAL_MINUTES` | `1440` | Cleanup interval |

### Infrastructure

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_MEMORY_LIMIT` | `4G` | Worker container memory limit |
| `WORKER_CPU_LIMIT` | `2.0` | Worker container CPU limit |
| `BACKEND_MEMORY_LIMIT` | `1G` | Backend container memory limit |
| `STUCK_TASK_TIMEOUT_MINUTES` | `30` | Auto-fail stuck documents after this duration |
| `BACKUP_HOST_DIR` | `./backups` | Host directory for PostgreSQL backups |
| `BACKUP_RETENTION_DAYS` | `7` | Backup retention |
| `BACKUP_INTERVAL_SECONDS` | `86400` | Backup frequency |

## Security

- **Security headers** on all responses (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy)
- **Rate limiting** on upload endpoints
- **MIME type validation** on file uploads
- **File size enforcement** (configurable `MAX_UPLOAD_MB`)
- **Optional virus scan hook** via `VIRUS_SCAN_COMMAND` (executed safely via subprocess)
- **Non-root containers** — both backend and frontend run as unprivileged users
- **CSV export escaping** — all CSV exports use proper quoting to prevent formula injection
- **Request ID tracking** — `X-Request-ID` header for audit trails
- **Celery task safety** — `task_acks_late`, `task_reject_on_worker_lost`, automatic stuck-document recovery

### Production Deployment

For production use, we recommend:

1. **Use a reverse proxy** (Caddy, nginx, or Traefik) for TLS termination
2. **Set strong PostgreSQL credentials** in `.env`
3. **Restrict `CORS_ORIGINS`** to your frontend domain
4. **Enable automated backups** — the `backup` service runs by default
5. **Monitor via Prometheus** — metrics available at `GET /metrics`

## Observability

- **Request IDs** echoed in `X-Request-ID` response header
- **Prometheus metrics** at `GET /metrics`
- **Structured logging** with request ID context
- **Status streaming** via SSE at `GET /documents/{id}/status/stream`

## Detected Patterns

The summary view extracts the following patterns when possible:

- Dates (multiple formats)
- Currency amounts (symbols, codes, totals — normalized)
- Invoice / Order IDs
- Emails and phone numbers
- Tax / VAT IDs

Extraction rules can be customized via `EXTRACTION_RULES_PATH` (JSON config).

## Tests

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm run test
```

## License

MIT License
