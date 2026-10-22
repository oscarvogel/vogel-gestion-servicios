SET NOCOUNT ON;

SELECT 'AUXCOL|' + CAST(c.column_id AS VARCHAR(5)) + '|' + c.name + '|' + TYPE_NAME(c.user_type_id)
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('dbo.Aux_PoliticasxArea')
  AND (c.name LIKE '%TipoTrabajo%' OR c.name LIKE '%Utilidad%' OR c.name LIKE '%Garantia%'
       OR c.name LIKE '%Liquid%' OR c.name LIKE '%ComisionEsCosto%' OR c.name LIKE '%Prioridad%'
       OR c.name IN ('ID','IDArea','Ppal','Codigo','Nombre','Area','Empresa','CodCli','PeriodoGarantia'))
ORDER BY c.column_id;

SELECT 'TRABAJOS_POL|' + COL_NAME(1,1) FROM sys.objects WHERE 1=0;

SELECT 'POL|' + CAST(P.ID AS VARCHAR(20)) + '|' + CAST(P.IDArea AS VARCHAR(20)) + '|ppal=' + CAST(P.Ppal AS VARCHAR(5))
     + '|' + ISNULL(P.Area,'(null)') + '|CodCli=' + ISNULL(CAST(P.CodCli AS VARCHAR(20)),'NULL')
     + '|Emp=' + ISNULL(P.Empresa,'(null)') + '|Gt=' + ISNULL(CAST(P.Garantia AS VARCHAR(5)),'NULL')
     + '|Util=' + ISNULL(CAST(P.Utilidad AS VARCHAR(5)),'NULL')
     + '|Liq=' + ISNULL(CAST(P.Liquidar AS VARCHAR(5)),'NULL')
     + '|EsCosto0=' + ISNULL(CAST(P.ComisionEsCosto0 AS VARCHAR(5)),'NULL')
     + '|EsCosto1=' + ISNULL(CAST(P.ComisionEsCosto1 AS VARCHAR(5)),'NULL')
     + '|EsCosto2=' + ISNULL(CAST(P.ComisionEsCosto2 AS VARCHAR(5)),'NULL')
     + '|EsCosto3=' + ISNULL(CAST(P.ComisionEsCosto3 AS VARCHAR(5)),'NULL')
FROM dbo.Aux_PoliticasxArea P
ORDER BY P.IDArea, P.Ppal;

SELECT 'DIST_UTILIDAD';
SELECT 'U|' + CAST(P.Utilidad AS VARCHAR(5)) + '|' + CAST(COUNT(*) AS VARCHAR(10))
FROM dbo.Aux_PoliticasxArea P GROUP BY P.Utilidad ORDER BY P.Utilidad;

SELECT 'DIST_ESC0';
SELECT 'E|' + ISNULL(CAST(P.ComisionEsCosto0 AS VARCHAR(5)),'NULL') + '|' + ISNULL(CAST(P.ComisionEsCosto1 AS VARCHAR(5)),'NULL')
     + '|' + ISNULL(CAST(P.ComisionEsCosto2 AS VARCHAR(5)),'NULL') + '|' + ISNULL(CAST(P.ComisionEsCosto3 AS VARCHAR(5)),'NULL')
     + '|' + CAST(COUNT(*) AS VARCHAR(10))
FROM dbo.Aux_PoliticasxArea P
GROUP BY P.ComisionEsCosto0, P.ComisionEsCosto1, P.ComisionEsCosto2, P.ComisionEsCosto3;
