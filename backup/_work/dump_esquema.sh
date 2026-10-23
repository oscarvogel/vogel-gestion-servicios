#!/bin/bash
# Vuelca el esquema completo de CiberBase a un archivo dentro del contenedor.
set -u
SA_PWD='Cb#Miercoles2026!x9'
CONTAINER='cb-sql'

q() {
  docker exec "$CONTAINER" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PWD" -d CiberBase -C -W -h -1 -s '|' -Q "$1"
}

OUT=/home/oscar/cb_restore/out
mkdir -p "$OUT"

q "
SET NOCOUNT ON;
SELECT s.name + '.' + t.name AS tabla, c.column_id AS ord, c.name AS columna,
       ty.name AS tipo, c.max_length AS len, c.precision AS prec, c.scale AS esc,
       CASE WHEN c.is_nullable = 1 THEN 'SI' ELSE 'NO' END AS nul,
       CASE WHEN c.is_identity = 1 THEN 'SI' ELSE '' END AS ident,
       ISNULL(dc.definition, '') AS def
FROM sys.columns c
JOIN sys.tables t ON t.object_id = c.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.default_constraints dc ON dc.object_id = c.default_object_id
WHERE t.is_ms_shipped = 0
ORDER BY s.name, t.name, c.column_id;
" > $OUT/esquema_cols.txt 2>&1

q "
SET NOCOUNT ON;
SELECT s.name + '.' + t.name AS tabla, i.name AS idx, i.is_primary_key AS pk, i.is_unique AS uniq,
       c.name AS columna, ic.key_ordinal AS ord
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE t.is_ms_shipped = 0 AND (i.is_primary_key = 1 OR i.is_unique = 1)
ORDER BY s.name, t.name, i.name, ic.key_ordinal;
" > $OUT/esquema_pk.txt 2>&1

q "
SET NOCOUNT ON;
SELECT s.name + '.' + t.name AS origen, pc.name AS col_origen,
       rs.name + '.' + rt.name AS destino, rc.name AS col_destino,
       fk.delete_referential_action_desc AS al_borrar
FROM sys.foreign_keys fk
JOIN sys.tables t ON t.object_id = fk.parent_object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
JOIN sys.schemas rs ON rs.schema_id = rt.schema_id
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
ORDER BY s.name, t.name, fk.name;
" > $OUT/esquema_fk.txt 2>&1

# Conteo de filas por tabla, con la consulta dinamica en una sola sentencia.
q "
SET NOCOUNT ON;
DECLARE @sql NVARCHAR(MAX) = N'';
SELECT @sql = @sql + N'UNION ALL SELECT N''' + s.name + N'.' + t.name + N''|T|' + CAST(COUNT_BIG(*) AS NVARCHAR(30)) + N' '
FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id WHERE t.is_ms_shipped = 0;
IF LEN(@sql) > 0 BEGIN SET @sql = STUFF(@sql, 1, 10, N''); EXEC sp_executesql @sql; END
" > $OUT/esquema_filas.txt 2>&1

# CHECK constraints: ahi suelen vivir las reglas de negocio (por ejemplo, garantias).
q "
SET NOCOUNT ON;
SELECT s.name + '.' + t.name AS tabla, cc.name AS chk, cc.definition AS def
FROM sys.check_constraints cc
JOIN sys.tables t ON t.object_id = cc.parent_object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
ORDER BY s.name, t.name, cc.name;
" > $OUT/esquema_checks.txt 2>&1

# Vistas y procedimientos: ahi vive la logica de liquidacion de comisiones.
q "
SET NOCOUNT ON;
SELECT o.name, o.type_desc FROM sys.objects o WHERE o.type IN ('V','P','FN','TF','IF','TR') ORDER BY o.type_desc, o.name;
" > $OUT/esquema_objetos.txt 2>&1

cat $OUT/esquema_cols.txt $OUT/esquema_pk.txt $OUT/esquema_fk.txt $OUT/esquema_filas.txt $OUT/esquema_checks.txt $OUT/esquema_objetos.txt > $OUT/esquema.txt 2>&1
wc -l $OUT/esquema_cols.txt $OUT/esquema_pk.txt $OUT/esquema_fk.txt $OUT/esquema_filas.txt $OUT/esquema_checks.txt $OUT/esquema_objetos.txt
echo "ESQUEMA_DONE"
