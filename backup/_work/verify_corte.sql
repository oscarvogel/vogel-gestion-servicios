SET NOCOUNT ON;

PRINT '=== VOLUMEN DEL CORTE 2020+ (por anio) ===';
SELECT YEAR(FechaAlta) AS anio, COUNT(*) AS ots,
       SUM(CASE WHEN Estado = 8 THEN 1 ELSE 0 END) AS terminadas_estado8,
       SUM(CASE WHEN Estado = 7 THEN 1 ELSE 0 END) AS cerradas_estado7,
       SUM(CASE WHEN Estado IS NULL THEN 1 ELSE 0 END) AS sin_estado,
       SUM(CASE WHEN CodCli = 0 THEN 1 ELSE 0 END) AS sin_cliente,
       SUM(CASE WHEN TrabajoRealizado IS NOT NULL AND LTRIM(RTRIM(TrabajoRealizado))<>'' THEN 1 ELSE 0 END) AS con_trabajo_realizado,
       SUM(CASE WHEN Intervienen > 0 THEN 1 ELSE 0 END) AS con_intervinientes
FROM dbo.CS_Trabajos WHERE YEAR(FechaAlta) >= 2020
GROUP BY YEAR(FechaAlta) ORDER BY anio;

PRINT '';
PRINT '=== TOTALES DEL CORTE 2020+ ===';
SELECT COUNT(*) AS ots_total,
       SUM(CASE WHEN Estado = 8 THEN 1 ELSE 0 END) AS terminadas,
       SUM(CASE WHEN Estado = 8 OR Estado = 7 THEN 1 ELSE 0 END) AS cerradas_o_terminadas,
       SUM(CASE WHEN CodCli = 0 THEN 1 ELSE 0 END) AS sin_cliente,
       COUNT(DISTINCT CodCli) AS clientes_distintos,
       MIN(FechaAlta) AS desde, MAX(FechaAlta) AS hasta
FROM dbo.CS_Trabajos WHERE YEAR(FechaAlta) >= 2020;

PRINT '';
PRINT '=== CLIENTES y EQUIPOS que tocan el corte 2020+ ===';
SELECT COUNT(*) AS clientes_en_clientes_tabla FROM dbo.CC_Clientes_Tabla;
SELECT COUNT(*) AS clientes_referenciados FROM (
  SELECT DISTINCT CodCli FROM dbo.CS_Trabajos WHERE YEAR(FechaAlta) >= 2020 AND CodCli > 0
) X;
SELECT COUNT(*) AS equipos_distintos FROM (
  SELECT DISTINCT CodCli, NroSerie FROM dbo.CS_Trabajos
  WHERE YEAR(FechaAlta) >= 2020 AND NroSerie IS NOT NULL AND NroSerie <> ''
    AND NroSerie NOT IN ('ILEGIBLE','FALTA','S/N','NO TIENE')
) Y;
SELECT COUNT(*) AS lineas_de_trabajo FROM dbo.CS_Partes
WHERE NroOrden IN (SELECT IDTrabajo FROM dbo.CS_Trabajos WHERE YEAR(FechaAlta) >= 2020);
SELECT COUNT(*) AS filas_intervienen FROM dbo.Intervienen
WHERE Orden IN (SELECT IDTrabajo FROM dbo.CS_Trabajos WHERE YEAR(FechaAlta) >= 2020);

PRINT '';
PRINT '=== MARCAS (areas) que tocan el corte 2020+ ===';
SELECT POL.Nombre AS marca, POL.Empresa, POL.CodCli AS facturar_a, CF.Cliente AS empresa_facturar,
       COUNT(*) AS ots, SUM(T.CostoTotal) AS costo
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
LEFT JOIN dbo.CC_Clientes_Tabla CF ON CF.CodCli = POL.CodCli
WHERE YEAR(T.FechaAlta) >= 2020
GROUP BY POL.Nombre, POL.Empresa, POL.CodCli, CF.Cliente
ORDER BY ots DESC;

PRINT '';
PRINT '=== CIERRE DE UN MES TIPO para validar: junio 2026 ===';
SELECT POL.CodCli AS facturar_a, CF.Cliente AS empresa_facturar, POL.Nombre AS marca,
       COUNT(*) AS ots, SUM(T.CostoTotal) AS costo, SUM(T.VentaTotal) AS venta
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
LEFT JOIN dbo.CC_Clientes_Tabla CF ON CF.CodCli = POL.CodCli
WHERE POL.Garantia = 1 AND T.FechaLista IS NOT NULL
  AND T.FechaLista >= '2026-06-01' AND T.FechaLista < '2026-07-01'
GROUP BY POL.CodCli, CF.Cliente, POL.Nombre ORDER BY costo DESC;
