# Changelog

All notable changes to VERA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Premium visual polish** across the frontend
  - Self-hosted Inter font — consistent typography, no external CDN dependency
  - Micro-interactions: button press feedback (`scale(0.98)`), card hover lift, modal entrance animations, card entrance animations
  - Skeleton loaders for OCR processing state (replaces plain alert)
  - Illustrated empty states with SVG icons
  - Modal backdrop blur effect (`blur(4px)`)
  - "from ai.doo" branded footer (bottom-left, fixed position, muted style)

## [1.2.0] - 2026-03-06

### Security

- **Fixed CSV injection vulnerability** in document and page exports — all CSV output now uses `csv.writer` with `QUOTE_ALL` to prevent formula injection in spreadsheet applications
- **Fixed command injection** in virus scan hook — replaced `os.system()` with `subprocess.run()` using argument list (no shell expansion)
- Security headers added to all API responses (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy)
- CORS middleware tightened — `allow_methods` and `allow_headers` now use explicit whitelists instead of wildcards
- Backend and frontend containers now run as non-root users (`vera`, UID 1001)

### Added

- Healthchecks on `backend`, `redis`, and `frontend` services — all five services now report health status
- Backend and worker now depend on healthy `postgres` and `redis` (not just container start)
- Frontend depends on healthy `backend`
- Celery `process_document` task now has `time_limit=600` and `soft_time_limit=540` to prevent indefinite hangs

### Changed

- Backend Dockerfile log level changed from `debug` to `info` for production use
- FastAPI version string updated from `0.1.0` to `1.2.0`
- README overhauled — corrected architecture section (PostgreSQL, not SQLite), added configuration reference tables, security section, and production deployment guide

## [1.1.0] - 2026-03-03

### Changed

- Ollama connectivity switched from `host.docker.internal:11434` to the shared `ollama_network` Docker network — fixes Linux Docker Engine where `host.docker.internal` is not available
- Default `OLLAMA_URL` in `docker-compose.yml` changed from `http://host.docker.internal:11434` to `http://ollama:11434` (internal DNS via `ollama_network`)
- `backend` and `worker` services now join both `default` and `ollama_network` networks; `frontend` is unchanged (it never calls Ollama directly)
- Ollama is managed by the standalone [OLLAMA repo](../OLLAMA) rather than run separately per-app
- Redis now runs with AOF persistence (`--appendonly yes --appendfsync everysec`) and a named `redis_data` volume — queued Celery tasks survive Redis restarts
- Celery worker now uses `task_acks_late=True` and `task_reject_on_worker_lost=True` — tasks are re-queued if the worker is killed mid-processing (OOM, container crash)
- `worker_prefetch_multiplier=1` set alongside `task_acks_late` to prevent task loss on multi-prefetch worker crash

### Added

- `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT` documented in `.env.example` with comments distinguishing Docker vs native dev usage
- `restart: unless-stopped` policy on all five services (`postgres`, `redis`, `backend`, `worker`, `frontend`) — services auto-recover from crashes and host reboots
- Memory/CPU resource limits on all services via `deploy.resources`; worker gets up to `WORKER_MEMORY_LIMIT` (default 4G) to accommodate PaddleOCR
- PostgreSQL `healthcheck` on the `postgres` service (used by the `backup` service dependency)
- `backup` service: scheduled `pg_dump` container that writes compressed `.sql.gz` backups to `BACKUP_HOST_DIR` (default `./backups`) every `BACKUP_INTERVAL_SECONDS` (default 24h) with `BACKUP_RETENTION_DAYS` (default 7) retention cleanup
- `scripts/backup.sh`: backup script used by the `backup` container
- `vera.recover_stuck_documents` Celery Beat task: runs every 5 minutes and auto-fails documents stuck in `processing` state longer than `STUCK_TASK_TIMEOUT_MINUTES` (default 30), with an `auto_failed` audit log entry per document
- New env vars documented in `.env.example`: `BACKUP_HOST_DIR`, `BACKUP_RETENTION_DAYS`, `BACKUP_INTERVAL_SECONDS`, `WORKER_MEMORY_LIMIT`, `WORKER_CPU_LIMIT`, `BACKEND_MEMORY_LIMIT`, `STUCK_TASK_TIMEOUT_MINUTES`

## [1.0.0] - 2026-02-06

### Added

- Initial stable release of VERA (Validated Extraction & Review Assistant)
- Support for JPG, PNG, and multi-page PDF uploads
- PaddleOCR local inference — offline, no cloud dependency, no data leaves the network
- Confidence-based token highlighting: high (≥0.92 auto-accept), medium (review suggested), low (blocks export until corrected)
- Inline correction UI — edit low-confidence tokens directly on the review page
- Validation hard gate — summaries and exports only unlock after explicit review completion
- Multi-page PDF support: per-page review and export; document-level summary/export requires all pages validated
- Offline detailed summaries with structured pattern extraction (dates, currency amounts, invoice/order IDs, emails, phone numbers, VAT IDs)
- Optional AI summaries via Ollama (toggled in Settings; gracefully falls back to offline summaries if Ollama is unreachable)
- SSE status streaming (`GET /documents/{id}/status/stream`) for real-time processing updates
- PostgreSQL database with Alembic migrations
- Celery + Redis async worker queue for non-blocking OCR processing
- Upload security: configurable size limit (`MAX_UPLOAD_MB=25`), MIME validation (`STRICT_MIME_VALIDATION`), optional virus scan hook (`VIRUS_SCAN_COMMAND`)
- Document retention policy: configurable trigger (`post_export` or `post_review`), mode (`delete` or `archive`), and interval
- Prometheus metrics at `GET /metrics`; request IDs echoed in `X-Request-ID`
- Full backend test suite (`pytest`) and frontend component tests (Vitest)

[1.2.0]: https://github.com/aidoo-systems/vera/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/aidoo-systems/vera/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/aidoo-systems/vera/releases/tag/v1.0.0
