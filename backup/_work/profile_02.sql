SET NOCOUNT ON;

PRINT '=== 11. QUE HACE UNICA A NumeroOrden? ===';
SELECT COUNT(*) AS filas, COUNT(DISTINCT NumeroOrden) AS solo_numero,
       COUNT(DISTINCT CAST(Lugar AS VARCHAR(10)) + N'|' + NumeroOrden) AS lugar_mas_numero,
       COUNT(DISTINCT CAST(YEAR(FechaOrden) AS VARCHAR(4)) + N'|' + NumeroOrden) AS anio_mas_numero,
       COUNT(DISTINCT CAST(Lugar AS VARCHAR(10)) + N'|' + CAST(YEAR(FechaOrden) AS VARCHAR(4)) + N'|' + NumeroOrden) AS lugar_anio_numero,
       COUNT(DISTINCT CAST(Sucursal AS VARCHAR(10)) + N'|' + NumeroOrden) AS sucursal_mas_numero
FROM CS_Trabajos WHERE NumeroOrden IS NOT NULL AND NumeroOrden <> '';

PRINT '';
PRINT '=== 12. LUGAR / SUCURSAL ===';
SELECT Lugar, COUNT(*) AS n FROM CS_Trabajos GROUP BY Lugar ORDER BY n DESC;
SELECT Sucursal, COUNT(*) AS n FROM CS_Trabajos GROUP BY Sucursal ORDER BY n DESC;

PRINT '';
PRINT '=== 13. NUMERO POR ANIO (muestra 2018-2026) ===';
SELECT YEAR(FechaOrden) AS anio, COUNT(*) AS n, COUNT(DISTINCT NumeroOrden) AS numeros,
       MIN(NumeroOrden) AS min_num, MAX(NumeroOrden) AS max_num
FROM CS_Trabajos WHERE NumeroOrden IS NOT NULL AND NumeroOrden <> ''
GROUP BY YEAR(FechaOrden) HAVING YEAR(FechaOrden) >= 2018 ORDER BY anio;

PRINT '';
PRINT '=== 14. TRABAJOS "LISTOS": cuanto historico hay ===';
SELECT YEAR(FechaAlta) AS anio,
       SUM(CASE WHEN Estado = 8 THEN 1 ELSE 0 END) AS estado8,
       SUM(CASE WHEN Estado = 6 THEN 1 ELSE 0 END) AS estado6,
       SUM(CASE WHEN Estado = 7 THEN 1 ELSE 0 END) AS estado7,
       COUNT(*) AS total
FROM CS_Trabajos WHERE YEAR(FechaAlta) >= 2019 GROUP BY YEAR(FechaAlta) ORDER BY anio;

PRINT '';
PRINT '=== 15. INTERVINIEN POR TRABAJO ===';
SELECT cnt AS intervenores, COUNT(*) AS trabajos FROM (
  SELECT Orden, COUNT(*) AS cnt FROM Intervienen GROUP BY Orden
) X GROUP BY cnt ORDER BY cnt;
SELECT COUNT(*) AS trabajos_sin_intervienen FROM CS_Trabajos T
WHERE NOT EXISTS (SELECT 1 FROM Intervienen I WHERE I.Orden = T.IDTrabajo);

PRINT '';
PRINT '=== 16. EQUIPO: agrupable por (cliente, serie)? ===';
SELECT COUNT(*) AS trabajos,
       COUNT(DISTINCT CAST(CodCli AS VARCHAR(20)) + N'|' + NroSerie) AS cliente_serie_distintos
FROM CS_Trabajos WHERE NroSerie IS NOT NULL AND NroSerie <> '' AND NroSerie NOT IN ('ILEGIBLE','FALTA','S/N','NO TIENE');
SELECT TOP 10 CodCli, NroSerie, COUNT(*) AS OTs, MIN(FechaAlta) AS primera, MAX(FechaAlta) AS ultima
FROM CS_Trabajos WHERE NroSerie IS NOT NULL AND NroSerie <> '' AND NroSerie NOT IN ('ILEGIBLE','FALTA','S/N','NO TIENE')
GROUP BY CodCli, NroSerie HAVING COUNT(*) > 1 ORDER BY OTs DESC;

PRINT '';
PRINT '=== 17. TRABAJOS CON CodCli INEXISTENTE ===';
SELECT TOP 10 T.CodCli, COUNT(*) AS n, MIN(T.Cliente) AS nombre_en_trabajo
FROM CS_Trabajos T LEFT JOIN CC_Clientes_Tabla C ON C.CodCli = T.CodCli
WHERE C.CodCli IS NULL GROUP BY T.CodCli ORDER BY n DESC;

PRINT '';
PRINT '=== 18. MUESTRA DE TRABAJOS ESTADO 8 ===';
SELECT TOP 8 IDTrabajo, NumeroOrden, Lugar, Estado, FechaOrden, FechaLista, FechaCerrada, FechaAlta,
       CodCli, Cliente, Equipo, Modelo, NroSerie, Garantia, DuracionGarantia, IDPolitica, Area, Sucursal,
       FacturaEmitida, Comprobante, FechaComprobante, TotalPresupuesto, VentaTotal, CostoTotal,
       VentaTotalComisiones, CostoTotalComisiones, Liquidada, FechaLiquidacion, LiquidacionNro,
       Intervienen, Responsable, TrabajoRealizado, Falla
FROM CS_Trabajos WHERE Estado = 8 AND TrabajoRealizado IS NOT NULL AND LTRIM(RTRIM(TrabajoRealizado)) <> ''
ORDER BY FechaAlta DESC;

PRINT '';
PRINT '=== 19. MONTO DE LAS TAREAS REALIZADAS (Estado 8) ===';
SELECT COUNT(*) AS n,
       SUM(CASE WHEN TotalPresupuesto IS NULL OR TotalPresupuesto = 0 THEN 1 ELSE 0 END) AS sin_presupuesto,
       SUM(CASE WHEN VentaTotal IS NULL OR VentaTotal = 0 THEN 1 ELSE 0 END) AS sin_venta,
       SUM(CASE WHEN CostoTotal IS NULL OR CostoTotal = 0 THEN 1 ELSE 0 END) AS sin_costo,
       SUM(CASE WHEN FacturaEmitida IS NOT NULL AND LTRIM(RTRIM(FacturaEmitida)) <> '' THEN 1 ELSE 0 END) AS con_factura,
       SUM(CASE WHEN FechaComprobante IS NOT NULL THEN 1 ELSE 0 END) AS con_fecha_comprobante
FROM CS_Trabajos WHERE Estado = 8;
