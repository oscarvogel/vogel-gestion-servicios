#!/bin/bash
# Consulta SQL de solo lectura contra CiberBase.
# Uso: q.sh <archivo.sql>
set -u
# La password de SA NO va en el repo. Se pasa por variable de entorno:
#   export CB_SA_PWD='<password de SA>'
SA_PWD="${CB_SA_PWD:?falta CB_SA_PWD: export CB_SA_PWD='<password de SA>'}"
CONTAINER='cb-sql'
SQLFILE="${1:?falta el archivo .sql}"
case "$SQLFILE" in
  /mnt/*) WINEQ="$SQLFILE" ;;
  *) WINEQ=$(wslpath -a "$SQLFILE" 2>/dev/null || echo "$SQLFILE") ;;
esac
docker cp "$WINEQ" "$CONTAINER:/tmp/query.sql" >/dev/null || exit 1
docker exec "$CONTAINER" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PWD" \
  -d CiberBase -C -W -h -1 -s '|' -i /tmp/query.sql
