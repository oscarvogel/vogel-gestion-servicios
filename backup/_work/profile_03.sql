SET NOCOUNT ON;

PRINT '=== 20. TRABAJOS INTERNOS (no son clientes) ===';
SELECT TOP 20 Cliente, COUNT(*) AS n FROM CS_Trabajos
WHERE Falla = 'TRABAJO INTERNO' OR Cliente = 'ELECTROTECNIREF'
GROUP BY Cliente ORDER BY n DESC;
SELECT COUNT(*) AS total_internos FROM CS_Trabajos WHERE Falla = 'TRABAJO INTERNO';
SELECT COUNT(*) AS total_por_cliente_0 FROM CS_Trabajos WHERE CodCli = 0;
SELECT COUNT(*) AS internalos_y_cliente_0 FROM CS_Trabajos WHERE (Falla = 'TRABAJO INTERNO') AND CodCli = 0;
SELECT COUNT(*) AS trabajos_0_sin_trabajo_interno FROM CS_Trabajos WHERE CodCli = 0 AND (Falla IS NULL OR Falla <> 'TRABAJO INTERNO');

PRINT '';
PRINT '=== 21. IDPolitica vs Area (son el mismo dominio?) ===';
SELECT COUNT(*) AS total,
       SUM(CASE WHEN IDPolitica = Area THEN 1 ELSE 0 END) AS iguales,
       SUM(CASE WHEN IDPolitica = 0 THEN 1 ELSE 0 END) AS politica_cero
FROM CS_Trabajos;
SELECT TOP 15 IDPolitica, COUNT(*) AS n, COUNT(DISTINCT Area) AS areas_distintas
FROM CS_Trabajos WHERE IDPolitica <> 0 GROUP BY IDPolitica ORDER BY n DESC;
SELECT TOP 15 Area, COUNT(*) AS n, COUNT(DISTINCT IDPolitica) AS politicas_distintas
FROM CS_Trabajos WHERE Area IS NOT NULL GROUP BY Area ORDER BY n DESC;

PRINT '';
PRINT '=== 22. Aux_PoliticasxArea: contenido ===';
SELECT TOP 20 * FROM Aux_PoliticasxArea ORDER BY 1;

PRINT '';
PRINT '=== 23. FACTURA EN EL TRABAJO ===';
SELECT COUNT(*) AS total,
       SUM(CASE WHEN FacturaEmitida IS NOT NULL AND LTRIM(RTRIM(FacturaEmitida)) <> '' THEN 1 ELSE 0 END) AS con_factura_emitida,
       SUM(CASE WHEN Comprobante IS NOT NULL AND LTRIM(RTRIM(Comprobante)) <> '' THEN 1 ELSE 0 END) AS con_comprobante,
       SUM(CASE WHEN FechaComprobante IS NOT NULL THEN 1 ELSE 0 END) AS con_fecha_comprobante,
       SUM(CASE WHEN NroDocumento IS NOT NULL AND LTRIM(RTRIM(NroDocumento)) <> '' THEN 1 ELSE 0 END) AS con_nro_documento,
       SUM(CASE WHEN Valor IS NOT NULL AND LTRIM(RTRIM(Valor)) <> '' THEN 1 ELSE 0 END) AS con_valor
FROM CS_Trabajos;
SELECT TOP 10 Estado, FacturaEmitida, Comprobante, FechaComprobante, NroDocumento, Valor, COUNT(*) AS n
FROM CS_Trabajos
WHERE FacturaEmitida IS NOT NULL AND LTRIM(RTRIM(FacturaEmitida)) <> ''
GROUP BY Estado, FacturaEmitida, Comprobante, FechaComprobante, NroDocumento, Valor ORDER BY n DESC;

PRINT '';
PRINT '=== 24. CS_UbicacionEquipoLog: que guarda ===';
SELECT TOP 5 * FROM CS_UbicacionEquipoLog;

PRINT '';
PRINT '=== 25. TRABAJOS MODERNOS (2023+) con datos de ejecucion ===';
SELECT COUNT(*) AS total,
       SUM(CASE WHEN I.Orden IS NOT NULL THEN 1 ELSE 0 END) AS con_interviene,
       SUM(CASE WHEN T.TrabajoRealizado IS NOT NULL AND LTRIM(RTRIM(T.TrabajoRealizado)) <> '' THEN 1 ELSE 0 END) AS con_trabajo_realizado,
       SUM(CASE WHEN T.VentaTotal IS NOT NULL AND T.VentaTotal <> 0 THEN 1 ELSE 0 END) AS con_venta,
       SUM(CASE WHEN T.FechaLista IS NOT NULL THEN 1 ELSE 0 END) AS con_fecha_lista,
       SUM(CASE WHEN T.FacturaEmitida IS NOT NULL AND LTRIM(RTRIM(T.FacturaEmitida)) <> '' THEN 1 ELSE 0 END) AS con_factura
FROM CS_Trabajos T LEFT JOIN (SELECT DISTINCT Orden FROM Intervienen) I ON I.Orden = T.IDTrabajo
WHERE YEAR(T.FechaAlta) >= 2023;

PRINT '';
PRINT '=== 26. EQUIPOS: el equipo vive en el trabajo o en una tabla aparte? ===';
SELECT COUNT(*) AS clientes_con_equipo FROM (
  SELECT CodCli, NroSerie FROM CS_Trabajos
  WHERE NroSerie IS NOT NULL AND NroSerie NOT IN ('ILEGIBLE','FALTA','S/N','NO TIENE')
  GROUP BY CodCli, NroSerie
) X;
SELECT COUNT(*) AS series_validas FROM (
  SELECT DISTINCT NroSerie FROM CS_Trabajos
  WHERE NroSerie IS NOT NULL AND NroSerie NOT IN ('ILEGIBLE','FALTA','S/N','NO TIENE')
) Y;
SELECT TOP 10 Equipo, COUNT(*) AS n FROM CS_Trabajos
WHERE Equipo IS NOT NULL AND LTRIM(RTRIM(Equipo)) <> '' GROUP BY Equipo ORDER BY n DESC;

PRINT '';
PRINT '=== 27. RESPONSABLE: quien recibe el equipo ===';
SELECT TOP 12 T.Responsable, COUNT(*) AS n FROM CS_Trabajos T
WHERE T.Responsable IS NOT NULL GROUP BY T.Responsable ORDER BY n DESC;
