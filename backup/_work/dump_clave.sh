#!/bin/bash
# Columnas de las tablas clave (query directo, sin SQL dinamico) + conteo de filas.
set -u
SA_PWD='Cb#Miercoles2026!x9'
CONTAINER='cb-sql'
OUT=/home/oscar/cb_restore/out

q() {
  docker exec "$CONTAINER" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PWD" -d CiberBase -C -W -h -1 -s '|' -Q "$1"
}

LIST="'CC_Usuarios','CS_Ubicaciones','CS_TipoUbicaciones','CS_UbicacionEquipoLog','Aux_PoliticasxArea','CS_PoliticasxArea','CS_LiquidacionesTecnicos_Tabla','CS_OrdenesLiquidadasTecnicos','CC_ComisionxUsuario','CC_PoliticasComisionVendedor','CS_Partes','CS_SucesosTrabajos','CC_Articulos','CS_AuditoriaTrabajos','CG_ItemsFacturas','CG_Presupuestos_Tabla','CC_CostoHistorico','CC_PreciosHistorico','CS_SucesosxPolitica','CS_CamposxPolitica'"

echo "### columnas de tablas clave ###"
q "
SET NOCOUNT ON;
SELECT t.name + N'|' + c.name + N'|' + ty.name + N'|' + CAST(c.max_length AS NVARCHAR(10)) + N'|' +
       CAST(c.precision AS NVARCHAR(10)) + N'|' + CAST(c.scale AS NVARCHAR(10)) + N'|' +
       CASE WHEN c.is_nullable = 1 THEN N'SI' ELSE N'NO' END + N'|' +
       CASE WHEN c.is_identity = 1 THEN N'SI' ELSE N'-' END
FROM sys.tables t
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE t.is_ms_shipped = 0 AND t.name IN ($LIST)
ORDER BY t.name, c.column_id;
" > $OUT/cols_clave.txt 2>&1

echo "### conteo de filas de tablas clave ###"
q "
SET NOCOUNT ON;
DECLARE @sql NVARCHAR(MAX);
DECLARE @name NVARCHAR(300);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR
  SELECT s.name + N'.' + t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
  WHERE t.is_ms_shipped = 0 AND t.name IN ($LIST) ORDER BY t.name;
OPEN c;
FETCH NEXT FROM c INTO @name;
WHILE @@FETCH_STATUS = 0
BEGIN
  SET @sql = N'SELECT N''' + REPLACE(@name, N'''', N'''''') + N''' AS tabla, CAST(COUNT_BIG(*) AS NVARCHAR(30)) AS filas FROM ' + QUOTENAME(PARSENAME(@name,2)) + N'.' + QUOTENAME(PARSENAME(@name,1));
  EXEC sp_executesql @sql;
  FETCH NEXT FROM c INTO @name;
END
CLOSE c; DEALLOCATE c;
" 2>&1

wc -l $OUT/cols_clave.txt
echo "CLAVE_DONE"
