#!/bin/bash
# Pipeline completo: espera la imagen, levanta SQL Server, restaura y vuelca el esquema.
set -u
SA_PWD='Cb#Miercoles2026!x9'
CONTAINER='cb-sql'
BAK='/bak/cyberbrain.bak'
DBNAME='CyberBrain'
OUT=/home/oscar/cb_restore/out
mkdir -p "$OUT"

echo "### 1. esperando imagen ###"
for i in $(seq 1 180); do
  if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q 'mssql/server'; then
    echo "imagen lista tras $i chequeos"
    break
  fi
  sleep 10
done
docker images --format '{{.Repository}}:{{.Tag}}' | grep -i mssql || { echo "FALLO: la imagen no llego"; exit 1; }

echo ""
echo "### 2. arrancando contenedor ###"
docker rm -f "$CONTAINER" >/dev/null 2>&1
docker run -d --name "$CONTAINER" \
  -e ACCEPT_EULA=Y -e "SA_PASSWORD=$SA_PWD" -e MSSQL_PID=Developer -e MSSQL_MEMORY_LIMIT_MB=4096 \
  -v /home/oscar/cb_restore:/bak \
  mcr.microsoft.com/mssql/server:2022-latest

echo "### 3. esperando SQL Server ###"
READY=0
for i in $(seq 1 90); do
  if docker exec "$CONTAINER" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PWD" -C -l 5 -Q "SELECT 1" >/dev/null 2>&1; then
    echo "listo tras $i intentos"; READY=1; break
  fi
  sleep 4
done
[ "$READY" = "1" ] || { echo "FALLO: SQL Server no respondio"; docker logs "$CONTAINER" | tail -30; exit 1; }

SQLCMD="docker exec $CONTAINER /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $SA_PWD -C -W -s '|' -h -1"

echo ""
echo "### 4. HEADERONLY ###"
$SQLCMD -Q "RESTORE HEADERONLY FROM DISK='$BAK'" 2>&1 | tee "$OUT/headeronly.txt"

echo ""
echo "### 5. FILELISTONLY ###"
$SQLCMD -Q "RESTORE FILELISTONLY FROM DISK='$BAK'" 2>&1 | tee "$OUT/filelistonly.txt"

echo ""
echo "### 6. RESTORE ###"
MOVES=""
while IFS='|' read -r logical ptype _rest; do
  [ -z "${logical:-}" ] && continue
  case "$ptype" in
    D) MOVES="${MOVES} MOVE '$logical' TO '/var/opt/mssql/data/${DBNAME}_${logical}.mdf', " ;;
    L) MOVES="${MOVES} MOVE '$logical' TO '/var/opt/mssql/data/${DBNAME}_${logical}_log.ldf', " ;;
  esac
done < <($SQLCMD -Q "RESTORE FILELISTONLY FROM DISK='$BAK'" 2>/dev/null)
MOVES="${MOVES%, }"
echo "MOVES=$MOVES"
$SQLCMD -Q "RESTORE DATABASE [$DBNAME] FROM DISK='$BAK' WITH $MOVES, RECOVERY, STATS=10" 2>&1 | tee "$OUT/restore.txt"

echo ""
echo "### 7. estado ###"
$SQLCMD -Q "SELECT name, state_desc, create_date FROM sys.databases;" 2>&1 | tee "$OUT/dbstate.txt"
echo "PIPELINE_DONE"
