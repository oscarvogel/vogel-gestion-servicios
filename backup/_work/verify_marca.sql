SET NOCOUNT ON;

PRINT '=== 1. ¿Hay objetos de liquidacion a MARCAS? ===';
SELECT o.name, o.type_desc FROM sys.objects o
WHERE o.type IN ('P','V','FN','TF','IF') AND (o.name LIKE '%Marca%' OR o.name LIKE '%Liquidac%')
ORDER BY o.name;

PRINT '';
PRINT '=== 2. Columnas reales de dbo.Areas ===';
SELECT c.name, ty.name, c.max_length FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id = OBJECT_ID(N'dbo.Areas') ORDER BY c.column_id;

PRINT '';
PRINT '=== 3. Las areas = marcas: a quien se le factura (CodCli de la politica) ===';
SELECT TOP 30 POL.ID, POL.Codigo, POL.Nombre AS area_marca, POL.Empresa AS empresa_marca,
       POL.CodCli AS cliente_a_facturar, C.Cliente AS nombre_cliente_facturar, POL.Garantia
FROM dbo.CS_PoliticasxArea POL
LEFT JOIN dbo.CC_Clientes_Tabla C ON C.CodCli = POL.CodCli
ORDER BY POL.ID;

PRINT '';
PRINT '=== 4. Cliente facturado por area: volumen y tipo ===';
SELECT DISTINCT POL.CodCli, C.Cliente, C.Tipo, C.Vendedor, C.ServiciosGarantia, C.Liquidar
FROM dbo.CS_PoliticasxArea POL LEFT JOIN dbo.CC_Clientes_Tabla C ON C.CodCli = POL.CodCli
WHERE POL.CodCli IS NOT NULL AND POL.CodCli > 0
ORDER BY POL.CodCli;

PRINT '';
PRINT '=== 5. VOLUMEN: OTs en garantia por mes y por marca (2025-2026) ===';
SELECT YEAR(T.FechaLista) AS anio, MONTH(T.FechaLista) AS mes,
       POL.Nombre AS marca, POL.Empresa,
       COUNT(*) AS ots_en_garantia,
       SUM(T.VentaTotal) AS venta_total,
       SUM(T.CostoTotal) AS costo_total
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
WHERE POL.Garantia = 1 AND T.FechaLista IS NOT NULL AND YEAR(T.FechaLista) >= 2025
GROUP BY YEAR(T.FechaLista), MONTH(T.FechaLista), POL.Nombre, POL.Empresa
ORDER BY anio, mes, ots_en_garantia DESC;

PRINT '';
PRINT '=== 6. Total por empresa facturadora (quien recibe la liquidacion) ===';
SELECT POL.CodCli AS cliente_facturar, C.Cliente AS empresa,
       COUNT(DISTINCT T.IDTrabajo) AS ots,
       SUM(T.VentaTotal) AS venta,
       SUM(T.CostoTotal) AS costo
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
LEFT JOIN dbo.CC_Clientes_Tabla C ON C.CodCli = POL.CodCli
WHERE POL.Garantia = 1 AND T.FechaLista IS NOT NULL AND YEAR(T.FechaLista) >= 2025
GROUP BY POL.CodCli, C.Cliente ORDER BY venta DESC;

PRINT '';
PRINT '=== 7. Coherencia: CS_Trabajos.Garantia vs POL.Garantia ===';
SELECT T.Garantia AS garantia_ot, POL.Garantia AS garantia_area, COUNT(*) AS n
FROM dbo.CS_Trabajos T JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
GROUP BY T.Garantia, POL.Garantia ORDER BY 1,2;

PRINT '';
PRINT '=== 8. Cierre mensual: cobertura de los campos que haria falta el reporte ===';
SELECT YEAR(T.FechaLista) AS anio, MONTH(T.FechaLista) AS mes,
       COUNT(*) AS ots,
       SUM(CASE WHEN T.FacturaEmitida IS NOT NULL AND LTRIM(RTRIM(T.FacturaEmitida))<>'' THEN 1 ELSE 0 END) AS con_factura_emitida,
       SUM(CASE WHEN T.Comprobante IS NOT NULL AND LTRIM(RTRIM(T.Comprobante))<>'' THEN 1 ELSE 0 END) AS con_comprobante,
       SUM(CASE WHEN T.Liquidada = 1 THEN 1 ELSE 0 END) AS liquidadas,
       SUM(CASE WHEN T.FechaCobrada IS NOT NULL THEN 1 ELSE 0 END) AS cobradas
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
WHERE POL.Garantia = 1 AND T.FechaLista IS NOT NULL AND YEAR(T.FechaLista) >= 2025
GROUP BY YEAR(T.FechaLista), MONTH(T.FechaLista) ORDER BY anio, mes;

PRINT '';
PRINT '=== 9. Un mes tipo: 20 lineas de detalle para un reporte de liquidacion ===';
SELECT TOP 20 T.IDTrabajo, T.FechaLista, T.FechaAlta, C.Cliente AS cliente_final,
       POL.Nombre AS marca, POL.CodCli AS facturar_a, CF.Cliente AS empresa_facturar,
       T.Equipo, T.Modelo, T.NroSerie, T.VentaTotal, T.CostoTotal, T.Liquidada, T.FacturaEmitida
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
LEFT JOIN dbo.CC_Clientes_Tabla C ON C.CodCli = T.CodCli
LEFT JOIN dbo.CC_Clientes_Tabla CF ON CF.CodCli = POL.CodCli
WHERE POL.Garantia = 1 AND T.FechaLista IS NOT NULL AND YEAR(T.FechaLista) = 2026 AND MONTH(T.FechaLista) = 6
ORDER BY T.FechaLista DESC;
