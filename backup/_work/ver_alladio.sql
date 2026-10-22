SET NOCOUNT ON;

SELECT 'COL|' + CAST(c.column_id AS VARCHAR(5)) + '|' + c.name + '|' + TYPE_NAME(c.user_type_id)
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('dbo.CS_PoliticasxArea')
ORDER BY c.column_id;

SELECT 'DEF|' + REPLACE(REPLACE(definition, CHAR(13), ' '), CHAR(10), ' ')
FROM sys.sql_modules WHERE object_id = OBJECT_ID('dbo.CS_PoliticasxArea');

SELECT 'TABLA|' + name FROM sys.tables WHERE name IN ('Partes','CS_Partes','Aux_PoliticasxArea');

SELECT 'AREAS_ALLADIO';
SELECT 'A|' + CAST(A.Codigo AS VARCHAR(20)) + '|' + A.Area + '|CodCli=' + ISNULL(CAST(A.CodCli AS VARCHAR(20)),'NULL')
     + '|Emp=' + ISNULL(A.Empresa,'(null)') + '|Gt3=' + CAST(A.GarantiasTerceros AS VARCHAR(5))
     + '|Liq=' + ISNULL(CAST(A.Liquidar AS VARCHAR(5)),'NULL') + '|Per=' + ISNULL(CAST(A.PeriodoGarantia AS VARCHAR(10)),'NULL')
FROM dbo.Areas A
WHERE A.CodCli = 7634 OR A.Area LIKE '%Alladio%' OR A.Empresa LIKE '%Alladio%'
ORDER BY A.Codigo;

SELECT 'AREAS_CON_CODCLI_Y_TIPO_TRABAJO';
SELECT 'P|' + CAST(P.IDPolitica AS VARCHAR(20)) + '|' + P.Area + '|CodCli=' + ISNULL(CAST(P.CodCli AS VARCHAR(20)),'NULL')
     + '|Emp=' + ISNULL(P.Empresa,'(null)') + '|Gt=' + ISNULL(CAST(P.Garantia AS VARCHAR(5)),'NULL')
     + '|Tipo=' + ISNULL(P.TipoTrabajo,'(null)') + '|Util=' + ISNULL(CAST(P.Utilidad AS VARCHAR(5)),'NULL')
     + '|Liq=' + ISNULL(CAST(P.Liquidar AS VARCHAR(5)),'NULL') + '|Per=' + ISNULL(CAST(P.PeriodoGarantia AS VARCHAR(10)),'NULL')
FROM dbo.CS_PoliticasxArea P
ORDER BY P.IDPolitica;
