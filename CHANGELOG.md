# Changelog

All notable changes to VERA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
