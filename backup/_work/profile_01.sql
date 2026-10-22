SET NOCOUNT ON;

PRINT '=== 1. RANGO DE FECHAS DE CS_Trabajos ===';
SELECT MIN(FechaOrden) AS min_orden, MAX(FechaOrden) AS max_orden,
       MIN(FechaAlta) AS min_alta, MAX(FechaAlta) AS max_alta,
       MIN(FechaCerrada) AS min_cerrada, MAX(FechaCerrada) AS max_cerrada,
       COUNT(*) AS total
FROM CS_Trabajos;

PRINT '';
PRINT '=== 2. ESTADO DE LOS TRABAJOS ===';
SELECT Estado, COUNT(*) AS n,
       SUM(CASE WHEN FechaLista IS NOT NULL THEN 1 ELSE 0 END) AS con_fecha_lista,
       SUM(CASE WHEN FechaCerrada IS NOT NULL THEN 1 ELSE 0 END) AS con_fecha_cerrada,
       SUM(CASE WHEN TrabajoRealizado IS NOT NULL AND LTRIM(RTRIM(TrabajoRealizado)) <> '' THEN 1 ELSE 0 END) AS con_trabajo_realizado
FROM CS_Trabajos GROUP BY Estado ORDER BY n DESC;

PRINT '';
PRINT '=== 3. TRABAJOS POR ANIO (FechaAlta) ===';
SELECT YEAR(FechaAlta) AS anio, COUNT(*) AS n
FROM CS_Trabajos WHERE FechaAlta IS NOT NULL GROUP BY YEAR(FechaAlta) ORDER BY anio;

PRINT '';
PRINT '=== 4. NUMERO DE ORDEN: unicidad ===';
SELECT COUNT(*) AS filas, COUNT(DISTINCT NumeroOrden) AS numeros_distintos,
       SUM(CASE WHEN NumeroOrden IS NULL OR LTRIM(RTRIM(NumeroOrden))='' THEN 1 ELSE 0 END) AS sin_numero
FROM CS_Trabajos;

PRINT '';
PRINT '=== 5. DUPLICADOS DE NumeroOrden (top 10) ===';
SELECT TOP 10 NumeroOrden, COUNT(*) AS n FROM CS_Trabajos
WHERE NumeroOrden IS NOT NULL GROUP BY NumeroOrden HAVING COUNT(*) > 1 ORDER BY n DESC;

PRINT '';
PRINT '=== 6. CALIDAD DEL CLIENTE Y DEL EQUIPO EN CS_Trabajos ===';
SELECT COUNT(*) AS total,
       SUM(CASE WHEN T.CodCli IS NULL THEN 1 ELSE 0 END) AS sin_codcli,
       SUM(CASE WHEN C.CodCli IS NOT NULL THEN 1 ELSE 0 END) AS codcli_existe_en_clientes,
       SUM(CASE WHEN T.Cliente IS NULL OR LTRIM(RTRIM(T.Cliente))='' THEN 1 ELSE 0 END) AS sin_nombre_cliente,
       SUM(CASE WHEN T.Equipo IS NULL OR LTRIM(RTRIM(T.Equipo))='' THEN 1 ELSE 0 END) AS sin_equipo,
       SUM(CASE WHEN T.Modelo IS NULL OR LTRIM(RTRIM(T.Modelo))='' THEN 1 ELSE 0 END) AS sin_modelo,
       SUM(CASE WHEN T.NroSerie IS NULL OR LTRIM(RTRIM(T.NroSerie))='' THEN 1 ELSE 0 END) AS sin_nro_serie,
       SUM(CASE WHEN T.Falla IS NULL OR LTRIM(RTRIM(T.Falla))='' THEN 1 ELSE 0 END) AS sin_falla,
       SUM(CASE WHEN T.TrabajoRealizado IS NULL OR LTRIM(RTRIM(T.TrabajoRealizado))='' THEN 1 ELSE 0 END) AS sin_trabajo_realizado
FROM CS_Trabajos T LEFT JOIN CC_Clientes_Tabla C ON C.CodCli = T.CodCli;

PRINT '';
PRINT '=== 7. SERIE: repetida entre trabajos? ===';
SELECT COUNT(*) AS total,
       COUNT(DISTINCT NroSerie) AS series_distintas,
       SUM(CASE WHEN NroSerie IS NOT NULL AND NroSerie <> '' THEN 1 ELSE 0 END) AS con_serie
FROM CS_Trabajos;
SELECT TOP 10 NroSerie, COUNT(*) AS n FROM CS_Trabajos
WHERE NroSerie IS NOT NULL AND NroSerie <> '' GROUP BY NroSerie HAVING COUNT(*) > 1 ORDER BY n DESC;

PRINT '';
PRINT '=== 8. CLIENTES: tipo y estado ===';
SELECT Tipo, COUNT(*) AS n FROM CC_Clientes_Tabla GROUP BY Tipo ORDER BY n DESC;
SELECT EstadoCuenta, COUNT(*) AS n FROM CC_Clientes_Tabla GROUP BY EstadoCuenta ORDER BY n DESC;
SELECT COUNT(*) AS total,
       SUM(CASE WHEN Vendedor IS NULL THEN 1 ELSE 0 END) AS sin_vendedor,
       SUM(CASE WHEN Liquidar = 1 THEN 1 ELSE 0 END) AS con_liquidar,
       SUM(CASE WHEN ServiciosGarantia = 1 THEN 1 ELSE 0 END) AS con_servicio_garantia,
       SUM(CASE WHEN ContactoPrincipal IS NULL THEN 1 ELSE 0 END) AS sin_contacto
FROM CC_Clientes_Tabla;

PRINT '';
PRINT '=== 9. CLIENTES DUPLICADOS POR NOMBRE ===';
SELECT COUNT(*) AS nombres_repetidos FROM (
  SELECT LTRIM(RTRIM(UPPER(Cliente))) AS nom, COUNT(*) c FROM CC_Clientes_Tabla
  WHERE Cliente IS NOT NULL AND LTRIM(RTRIM(Cliente)) <> '' GROUP BY LTRIM(RTRIM(UPPER(Cliente))) HAVING COUNT(*) > 1
) X;
SELECT TOP 10 LTRIM(RTRIM(UPPER(Cliente))) AS nombre, COUNT(*) AS n FROM CC_Clientes_Tabla
WHERE Cliente IS NOT NULL AND LTRIM(RTRIM(Cliente)) <> ''
GROUP BY LTRIM(RTRIM(UPPER(Cliente))) HAVING COUNT(*) > 1 ORDER BY n DESC;

PRINT '';
PRINT '=== 10. CUIT: el documento del cliente vive en CG_Facturas_Tabla ===';
SELECT COUNT(*) AS clientes,
       SUM(CASE WHEN f.CUIT IS NOT NULL AND f.CUIT <> '' THEN 1 ELSE 0 END) AS con_cuit
FROM CC_Clientes_Tabla c
LEFT JOIN (SELECT CodCli, MAX(CUIT) AS CUIT FROM CG_Facturas_Tabla GROUP BY CodCli) f ON f.CodCli = c.CodCli;
SELECT TOP 10 CodCli, CUIT, COUNT(*) AS n FROM CG_Facturas_Tabla
WHERE CUIT IS NOT NULL AND CUIT <> '' GROUP BY CodCli, CUIT ORDER BY n DESC;
