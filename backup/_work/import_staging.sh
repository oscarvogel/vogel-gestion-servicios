#!/bin/bash
# Importa el dump de la base local (con los datos de CiberBrain) en el MySQL de staging.
#
# Uso: import_staging.sh <host> <puerto> <usuario> <base>
# El password llega por variable de entorno STAGING_DB_PASSWORD.
set -euo pipefail

HOST="$1"; PORT="$2"; USER="$3"; DB="$4"
PWD="${STAGING_DB_PASSWORD:?falta STAGING_DB_PASSWORD}"
DUMP=/mnt/c/Programacion/vogel-gestion/backup/_work/dump_local_cierre.sql

# El cliente MySQL 8 del contenedor vogel-mysql habla con el 8.4 de staging
# (el de MariaDB que trae WSL no soporta caching_sha2_password).
q() {
  docker exec -e MYSQL_PWD="$PWD" vogel-mysql mysql \
    -h "$HOST" -P "$PORT" -u "$USER" -N -B "$@"
}

echo "== antes =="
q -e "select count(*) from information_schema.tables where table_schema='$DB';"

echo "== importando (puede tardar) =="
docker exec -e MYSQL_PWD="$PWD" -i vogel-mysql mysql \
  -h "$HOST" -P "$PORT" -u "$USER" \
  --default-character-set=utf8mb4 \
  --max-allowed-packet=512M \
  "$DB" < "$DUMP"

echo "== despues =="
q -e "select 'work_orders', count(*) from $DB.work_orders
       union all select 'customers', count(*) from $DB.customers
       union all select 'work_order_parts', count(*) from $DB.work_order_parts
       union all select 'work_order_technicians', count(*) from $DB.work_order_technicians
       union all select 'companies', count(*) from $DB.companies
       union all select 'users', count(*) from $DB.users
       union all select 'work_areas', count(*) from $DB.work_areas
       union all select 'sellers', count(*) from $DB.sellers
       union all select 'technicians', count(*) from $DB.technicians
       union all select 'invoices', count(*) from $DB.invoices;"

echo "== version de migraciones =="
q -e "select version_num from $DB.alembic_version;"
