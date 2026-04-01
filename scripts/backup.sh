#!/bin/sh
set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILE="${BACKUP_DIR}/vera-${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"
echo "[$(date)] Starting backup → $FILE"
pg_dump -h postgres -U "${POSTGRES_USER:-vera}" "${POSTGRES_DB:-vera}" | gzip > "$FILE"

# Validate backup is non-empty (pg_dump failure produces a near-empty gzip header)
BACKUP_SIZE=$(stat -c%s "$FILE" 2>/dev/null || stat -f%z "$FILE" 2>/dev/null || echo 0)
if [ "$BACKUP_SIZE" -lt 512 ]; then
    echo "[$(date)] ERROR: Backup file too small (${BACKUP_SIZE} bytes) — pg_dump may have failed"
    rm -f "$FILE"
    exit 1
fi
echo "[$(date)] Backup complete: $(du -sh "$FILE" | cut -f1)"
# To restore: gunzip -c <backup-file> | psql -h postgres -U vera vera

# Retention cleanup
find "$BACKUP_DIR" -name "vera-*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete
echo "[$(date)] Cleaned up backups older than ${RETENTION_DAYS} days"
