#!/bin/sh
set -e

echo "[entrypoint] Running Alembic migrations..."
# If the database already has tables but no alembic_version table (e.g. a pre-migration
# deployment), stamp it at head so Alembic knows the schema is current, then upgrade
# normally to pick up any newer migrations.
if ! alembic upgrade head 2>&1; then
    echo "[entrypoint] Migration failed — stamping existing schema at head and retrying..."
    alembic stamp head
    alembic upgrade head
fi
echo "[entrypoint] Migrations complete. Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info --access-log
