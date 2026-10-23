SET NOCOUNT ON;

PRINT '=== G. COMPROBANTE con formato factura: distribucion por anio ===';
SELECT YEAR(FechaAlta) AS anio,
       COUNT(*) AS total,
       SUM(CASE WHEN Comprobante LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' THEN 1 ELSE 0 END) AS con_formato_factura,
       SUM(CASE WHEN FacturaEmitida IS NOT NULL AND LTRIM(RTRIM(FacturaEmitida))<>'' THEN 1 ELSE 0 END) AS con_factura_emitida
FROM CS_Trabajos WHERE YEAR(FechaAlta) >= 2019 GROUP BY YEAR(FechaAlta) ORDER BY anio;

PRINT '';
PRINT '=== H. HAY QUE TRAMPA: Comprobante con formato factura y FechaComprobante ===';
SELECT COUNT(*) AS n,
       SUM(CASE WHEN FechaComprobante IS NOT NULL THEN 1 ELSE 0 END) AS con_fecha,
       SUM(CASE WHEN FacturaEmitida IS NOT NULL AND LTRIM(RTRIM(FacturaEmitida))<>'' THEN 1 ELSE 0 END) AS ademas_con_factura_emitida
FROM CS_Trabajos
WHERE Comprobante LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]';

PRINT '';
PRINT '=== I. ¿EXISTE ESA FACTURA EN CG_Facturas_Tabla? (control) ===';
SELECT COUNT(*) AS comprobantes_formato_factura,
       (SELECT COUNT(*) FROM CS_Trabajos T2
        WHERE T2.Comprobante LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
          AND EXISTS (SELECT 1 FROM CG_Facturas_Tabla F WHERE F.Numero = T2.Comprobante)) AS existen_en_tabla_facturas
FROM CS_Trabajos T
WHERE T.Comprobante LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]';

PRINT '';
PRINT '=== J. ¿CS_FacturarOrden / CS_GenerarFacturaTrabajo escriben en Comprobante? (fuente) ===';
SELECT TOP 20 o.name, CASE WHEN m.definition LIKE '%Comprobante%' THEN 'SI' ELSE 'no' END AS menciona_comprobante
FROM sys.objects o JOIN sys.sql_modules m ON m.object_id = o.object_id
WHERE o.type IN ('P','V','FN','TF','IF') AND o.name LIKE 'CS_%Factur%'
ORDER BY o.name;

PRINT '';
PRINT '=== K. COMPROBANTES: que valores hay en total (top 30) ===';
SELECT TOP 30
  CASE
    WHEN Comprobante IS NULL OR LTRIM(RTRIM(Comprobante))='' THEN '(vacio)'
    WHEN Comprobante LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' THEN 'FORMATO FACTURA'
    WHEN Comprobante LIKE 'STOCK' THEN 'STOCK'
    ELSE 'OTRO: ' + Comprobante END AS tipo,
  COUNT(*) AS n, MIN(FechaAlta) AS desde, MAX(FechaAlta) AS hasta
FROM CS_Trabajos GROUP BY
  CASE
    WHEN Comprobante IS NULL OR LTRIM(RTRIM(Comprobante))='' THEN '(vacio)'
    WHEN Comprobante LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' THEN 'FORMATO FACTURA'
    WHEN Comprobante LIKE 'STOCK' THEN 'STOCK'
    ELSE 'OTRO: ' + Comprobante END
ORDER BY n DESC;
