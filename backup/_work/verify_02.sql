SET NOCOUNT ON;

PRINT '=== A. FACTURAS: ultimo ano ===';
SELECT YEAR(Fecha) AS anio, COUNT(*) AS n FROM CG_Facturas_Tabla GROUP BY YEAR(Fecha) ORDER BY anio;

PRINT '';
PRINT '=== B. TRABAJOS CON FacturaEmitida por anio (segun FechaAlta) ===';
SELECT YEAR(FechaAlta) AS anio, COUNT(*) AS total,
       SUM(CASE WHEN FacturaEmitida IS NOT NULL AND LTRIM(RTRIM(FacturaEmitida))<>'' THEN 1 ELSE 0 END) AS con_factura_emitida,
       SUM(CASE WHEN Comprobante IS NOT NULL AND LTRIM(RTRIM(Comprobante))<>'' THEN 1 ELSE 0 END) AS con_comprobante
FROM CS_Trabajos WHERE YEAR(FechaAlta) >= 2019 GROUP BY YEAR(FechaAlta) ORDER BY anio;

PRINT '';
PRINT '=== C. QUE HAY DESPUES DE 2021-07 en Comprobante? ===';
SELECT TOP 25 Comprobante, COUNT(*) AS n, MIN(FechaAlta) AS desde, MAX(FechaAlta) AS hasta
FROM CS_Trabajos
WHERE YEAR(FechaAlta) >= 2021 AND Comprobante IS NOT NULL AND LTRIM(RTRIM(Comprobante)) <> ''
GROUP BY Comprobante ORDER BY n DESC;

PRINT '';
PRINT '=== D. FACTURAS: hay otra tabla de ventas reciente? ===';
SELECT s.name + N'.' + t.name AS tabla, COUNT(*) AS n FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
WHERE t.is_ms_shipped=0 AND (t.name LIKE N'%Factura%' OR t.name LIKE N'%Venta%' OR t.name LIKE N'%Comprobante%')
GROUP BY s.name, t.name ORDER BY n DESC;

PRINT '';
PRINT '=== E. PRESUPUESTOS: rango de fechas ===';
SELECT YEAR(Fecha) AS anio, COUNT(*) AS n FROM CG_Presupuestos_Tabla WHERE Fecha IS NOT NULL GROUP BY YEAR(Fecha) ORDER BY anio;

PRINT '';
PRINT '=== F. ULTIMOS TRABAJOS 2026 (muestra) ===';
SELECT TOP 8 IDTrabajo, Estado, FechaAlta, Cliente, Equipo, NroSerie, FacturaEmitida, Comprobante, FechaComprobante, VentaTotal, Liquidada
FROM CS_Trabajos WHERE YEAR(FechaAlta) = 2026 ORDER BY FechaAlta DESC;
