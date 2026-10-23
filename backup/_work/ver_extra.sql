SET NOCOUNT ON;

SELECT 'INV_COLS_30+';
SELECT CAST(c.column_id AS VARCHAR(10)) + '|' + c.name + '|' + TYPE_NAME(c.user_type_id)
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('dbo.CG_Facturas_Tabla') AND c.column_id >= 30
ORDER BY c.column_id;

SELECT 'MONEDAS_COLS';
SELECT CAST(c.column_id AS VARCHAR(10)) + '|' + c.name
FROM sys.columns c WHERE c.object_id = OBJECT_ID('dbo.CC_Monedas') ORDER BY c.column_id;

SELECT 'INTERVIENEN_PERSONAS';
SELECT 'I|' + CAST(COUNT(DISTINCT I.Persona) AS VARCHAR(20)) + '|huerfanos=' + CAST(COUNT(DISTINCT CASE WHEN U.Codigo IS NULL THEN I.Persona END) AS VARCHAR(20))
FROM dbo.Intervienen I LEFT JOIN dbo.CC_Usuarios U ON U.Codigo = I.Persona;

SELECT 'ESTADOS_REVISADOS';
SELECT 'E|' + CAST(ISNULL(CAST(T.Estado AS VARCHAR(5)),'NULL') AS VARCHAR(10)) + '|' + CAST(COUNT(*) AS VARCHAR(20))
FROM dbo.CS_Trabajos T
WHERE T.FechaAlta >= '20200101'
GROUP BY T.Estado ORDER BY T.Estado;
