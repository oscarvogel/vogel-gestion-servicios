SET NOCOUNT ON;

SELECT 'TAREAS';
SELECT CAST(T.ID AS VARCHAR(10)) + '|' + T.Tarea + '|' + ISNULL(T.Descripcion,'')
FROM dbo.CC_Tareas T ORDER BY T.ID;

SELECT 'COLS_CS_TRABAJOS_RELEVANTES';
SELECT c.name + '|' + TYPE_NAME(c.user_type_id)
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('dbo.CS_Trabajos')
  AND (c.name LIKE '%Presupuesto%' OR c.name LIKE '%Total%' OR c.name LIKE '%Factura%' OR c.name LIKE '%Comprob%' OR c.name LIKE '%Liquid%')
ORDER BY c.column_id;

SELECT 'MUESTRA_FACTURAEMITIDA';
SELECT TOP 12 'W|' + ISNULL(T.FacturaEmitida,'') + '|Comp=' + ISNULL(T.Comprobante,'') + '|Fecha=' + CONVERT(VARCHAR(19), T.FechaLista, 120) + '|Id=' + CAST(T.IDTrabajo AS VARCHAR(20))
FROM dbo.CS_Trabajos T
WHERE T.FacturaEmitida IS NOT NULL AND T.FacturaEmitida <> ''
ORDER BY T.IDTrabajo DESC;

SELECT 'MUESTRA_NUMERO_FACTURA';
SELECT TOP 12 'F|' + F.Numero + '|' + CAST(F.CodCli AS VARCHAR(20)) + '|' + CONVERT(VARCHAR(19), F.Fecha, 120) + '|Total=' + CAST(F.Total AS VARCHAR(30))
FROM dbo.CG_Facturas_Tabla F ORDER BY F.ID DESC;

SELECT 'COMPARACION_NUMEROS';
SELECT 'C|numFacturaTabla=' + CAST(COUNT(*) AS VARCHAR(20))
FROM dbo.CS_Trabajos T
WHERE T.FacturaEmitida IS NOT NULL AND T.FacturaEmitida <> ''
  AND EXISTS (SELECT 1 FROM dbo.CG_Facturas_Tabla F WHERE F.Numero = T.FacturaEmitida);

SELECT 'CG_ITEMSFACTURAS_COLS';
SELECT c.name + '|' + TYPE_NAME(c.user_type_id)
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('dbo.CG_ItemsFacturas')
ORDER BY c.column_id;
