#!/bin/bash
# Restaura CiberBase construyendo la clausula MOVE desde msdb.dbo.restorefilelist.
set -u
SA_PWD='Cb#Miercoles2026!x9'
CONTAINER='cb-sql'
BAK='/bak/cyberbrain.bak'
DBNAME='CiberBase'
OUT=/home/oscar/cb_restore/out
mkdir -p "$OUT"

SQLCMD="docker exec $CONTAINER /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $SA_PWD -C -W -h -1 -s|"

echo "############ FILELISTONLY (tabla del sistema) ############"
$SQLCMD -Q "RESTORE FILELISTONLY FROM DISK='$BAK'; SELECT LogicalName, Type FROM msdb.dbo.restorefilelist;" 2>&1 | tee "$OUT/filelist.txt"

echo ""
echo "############ RESTORE (MOVE armado en T-SQL) ############"
$SQLCMD -Q "
DECLARE @moves NVARCHAR(MAX) = N'';
SELECT @moves = @moves + CASE WHEN LEN(@moves) > 0 THEN N', ' ELSE N'' END
    + N'MOVE ' + QUOTENAME(LogicalName) + N' TO ' +
      CASE WHEN Type = 'D' THEN N'''', ELSE N'''' END
  FROM msdb.dbo.restorefilelist;
PRINT N'MOVES=' + @moves;
" 2>&1

echo ""
echo "############ RESTORE real ############"
$SQLCMD -Q "
RESTORE DATABASE [$DBNAME] FROM DISK='$BAK'
WITH MOVE 'CiberBase_Datos' TO '/var/opt/mssql/data/CiberBase_Datos.mdf',
     MOVE 'CiberBase_Registro' TO '/var/opt/mssql/data/CiberBase_Registro_log.ldf',
     RECOVERY, STATS=10;
" 2>&1 | tee "$OUT/restore.txt"

echo ""
echo "############ ESTADO ############"
$SQLCMD -Q "SELECT name, state_desc, create_date, collation_name FROM sys.databases;" 2>&1 | tee "$OUT/dbstate.txt"
echo "RESTORE_STEP_DONE"
