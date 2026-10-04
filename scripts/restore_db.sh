#!/usr/bin/env bash
# Восстановление БД из дампа: ./scripts/restore_db.sh backups/<файл>.sql.gz

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Использование: $0 <путь-к-файлу-бэкапа.sql.gz>"
  exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
  echo "Файл не найден: $BACKUP_FILE"
  exit 1
fi

POSTGRES_USER="${POSTGRES_USER:-window_user}"
POSTGRES_DB="${POSTGRES_DB:-window_landing}"

read -r -p "Это ПЕРЕЗАПИШЕТ текущую БД '${POSTGRES_DB}' данными из ${BACKUP_FILE}. Продолжить? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Отменено."
  exit 0
fi

echo "Восстанавливаю БД из ${BACKUP_FILE}..."
gunzip -c "$BACKUP_FILE" | docker compose exec -T db psql -U "${POSTGRES_USER}" "${POSTGRES_DB}"

echo "Восстановление завершено."
