#!/bin/sh
set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILE="${BACKUP_DIR}/vera-${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"
echo "[$(date)] Starting backup → $FILE"
pg_dump -h postgres -U "${POSTGRES_USER:-vera}" "${POSTGRES_DB:-vera}" | gzip > "$FILE"
echo "[$(date)] Backup complete: $(du -sh "$FILE" | cut -f1)"

# Retention cleanup
find "$BACKUP_DIR" -name "vera-*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete
echo "[$(date)] Cleaned up backups older than ${RETENTION_DAYS} days"
