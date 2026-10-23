#!/bin/bash
# Dump de la base local (vogel-mysql en WSL) para llevar los datos a staging.
set -euo pipefail

DEST=/mnt/c/Programacion/vogel-gestion/backup/_work/dump_local_cierre.sql

docker exec vogel-mysql mysqldump \
  -u vogel -pchange_me \
  --single-transaction \
  --no-tablespaces \
  --routines --triggers --events \
  --add-drop-table \
  --default-character-set=utf8mb4 \
  vogel_gestion_servicios > "$DEST" 2>/tmp/dumperr.txt || {
    echo "FALLO el dump:"; cat /tmp/dumperr.txt; exit 1;
  }

echo "OK dump"
ls -lh "$DEST"
echo "tablas: $(grep -c '^CREATE TABLE' "$DEST")"
echo "inserts: $(grep -c 'INSERT INTO' "$DEST")"
