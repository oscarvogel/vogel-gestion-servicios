#!/usr/bin/env bash
# Exporta el corte 2020+ del legacy (CiberBase, SQL Server) a TSV en backup/_work/csv/.
#
# Es la fase 1 del importador: deja un snapshot auditable y reejecutable. La fase 2
# (backend/scripts/import_cyberbrain.py) lee esos TSV y escribe en MySQL.
#
# El separador es '|' y los textos libres vienen sanitizados desde el SQL (sin CR, sin LF
# y sin '|'), asi que el archivo se parsea con split('|').
set -euo pipefail

# La password de SA NO va en el repo. Se pasa por variable de entorno:
#   export CB_SA_PWD='<password de SA>'
SA_PWD="${CB_SA_PWD:?falta CB_SA_PWD: export CB_SA_PWD='<password de SA>'}"
CONTAINER='cb-sql'
DB='CiberBase'
SQLCMD='/opt/mssql-tools18/bin/sqlcmd'

RAIZ='/mnt/c/Programacion/vogel-gestion/backup/_work'
SQL_DIR="$RAIZ/sql"
CSV_DIR="$RAIZ/csv"

mkdir -p "$CSV_DIR"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "ERROR: el contenedor $CONTAINER no esta corriendo (arrancalo con docker start $CONTAINER)"
    exit 1
fi

for f in "$SQL_DIR"/*.sql; do
    name=$(basename "$f" .sql)
    printf '%-18s ' "$name"
    docker cp "$f" "$CONTAINER:/tmp/$name.sql" >/dev/null
    # -y 0 = sin truncar columnas; -s '|' = separador; -W no se usa porque es incompatible con -y.
    # La redireccion la hace esta shell (WSL), asi que el archivo cae en el filesystem de Windows.
    docker exec "$CONTAINER" "$SQLCMD" -S localhost -U sa -P "$SA_PWD" -d "$DB" -C -y 0 -s '|' \
        -i "/tmp/$name.sql" > "$CSV_DIR/$name.tsv"
    if grep -qi 'Msg ' "$CSV_DIR/$name.tsv"; then
        echo "ERROR de SQL:"
        grep -i 'Msg ' "$CSV_DIR/$name.tsv" | head -5
        exit 1
    fi
    echo "$(wc -l < "$CSV_DIR/$name.tsv") lineas"
done

echo "listo -> $CSV_DIR"
