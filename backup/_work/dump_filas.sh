#!/bin/bash
# Lista tablas con su conteo de filas (cursor + PRINT, sin SQL dinamico fragile).
set -u
SA_PWD='Cb#Miercoles2026!x9'
CONTAINER='cb-sql'
OUT=/home/oscar/cb_restore/out
mkdir -p "$OUT"

q() {
  docker exec "$CONTAINER" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PWD" -d CiberBase -C -W -h -1 -s '|' -Q "$1"
}

q "
SET NOCOUNT ON;
DECLARE @sql NVARCHAR(MAX);
DECLARE @name NVARCHAR(300);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR
  SELECT s.name + N'.' + t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
  WHERE t.is_ms_shipped = 0 ORDER BY t.name;
OPEN c;
FETCH NEXT FROM c INTO @name;
WHILE @@FETCH_STATUS = 0
BEGIN
  SET @sql = N'SELECT N''' + REPLACE(@name, N'''', N'''''') + N''' AS tabla, COUNT_BIG(*) AS filas FROM ' + QUOTENAME(PARSENAME(@name, 2)) + N'.' + QUOTENAME(PARSENAME(@name, 1));
  EXEC sp_executesql @sql;
  FETCH NEXT FROM c INTO @name;
END
CLOSE c; DEALLOCATE c;
" > $OUT/filas.txt 2>&1

echo "--- total tablas ---"
grep -c "|" $OUT/filas.txt
echo "--- tablas con 0 filas ---"
grep -c "|0$" $OUT/filas.txt
sort -t'|' -k2 -n -r $OUT/filas.txt | head -60
echo "TABLAS_DONE"
