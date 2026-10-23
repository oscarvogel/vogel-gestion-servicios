#!/usr/bin/env bash
# Levanta el MySQL 8.4 local (parámetros del docker-compose.yml) para probar la
# migración + importador sin tocar staging ni producción.
set -euo pipefail

NAME=vogel-mysql
DB=vogel_gestion_servicios
USER=vogel
PASS=change_me
ROOT=change_root
# El 3306 del host WSL lo tiene el MariaDB del sistema; el contenedor va al 3307.
HOST_PORT=3307

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    docker rm -f "$NAME" >/dev/null
fi

docker run -d --name "$NAME" \
    -e MYSQL_DATABASE="$DB" \
    -e MYSQL_USER="$USER" \
    -e MYSQL_PASSWORD="$PASS" \
    -e MYSQL_ROOT_PASSWORD="$ROOT" \
    -p ${HOST_PORT}:3306 \
    --health-cmd="mysqladmin ping -h localhost" \
    --health-interval=5s --health-timeout=5s --health-retries=30 \
    mysql:8.4

echo "contenedor arrancado, esperando healthy..."
for i in $(seq 1 60); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$NAME" 2>/dev/null || echo "none")
    if [ "$status" = "healthy" ]; then
        echo "healthy en ${i}s"
        exit 0
    fi
    sleep 1
done

echo "TIMEOUT esperando healthy (estado actual: ${status})"
docker logs --tail 20 "$NAME"
exit 1
