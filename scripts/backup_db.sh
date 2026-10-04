#!/usr/bin/env bash
# Дамп PostgreSQL из контейнера db в ./backups/ (хранятся последние 14).

set -euo pipefail

BACKUP_DIR="$(dirname "$0")/../backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
FILENAME="$BACKUP_DIR/leads_${TIMESTAMP}.sql.gz"

POSTGRES_USER="${POSTGRES_USER:-window_user}"
POSTGRES_DB="${POSTGRES_DB:-window_landing}"

echo "Создаю бэкап БД '${POSTGRES_DB}' -> ${FILENAME}"

docker compose exec -T db pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${FILENAME}"

echo "Готово: ${FILENAME}"

ls -1t "${BACKUP_DIR}"/leads_*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
