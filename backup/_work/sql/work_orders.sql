SET NOCOUNT ON;
-- Ordenes de trabajo del corte 2020+ (dbo.CS_Trabajos).
-- El corte es por FechaAlta >= 2020-01-01.
SELECT
    CAST(T.IDTrabajo AS VARCHAR(20))          AS id_trabajo,
    ISNULL(REPLACE(REPLACE(REPLACE(T.NumeroOrden, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS numero_orden,
    ISNULL(CAST(T.CodCli AS VARCHAR(20)), '')  AS codcli,
    ISNULL(REPLACE(REPLACE(REPLACE(T.NroSerie, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS nro_serie,
    ISNULL(REPLACE(REPLACE(REPLACE(T.Equipo, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS equipo,
    ISNULL(REPLACE(REPLACE(REPLACE(T.Modelo, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS modelo,
    ISNULL(REPLACE(REPLACE(REPLACE(T.Cliente, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS cliente,
    REPLACE(REPLACE(REPLACE(ISNULL(T.Falla, N''), NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS falla,
    ISNULL(CAST(T.Estado AS VARCHAR(5)), '')  AS estado,
    CONVERT(VARCHAR(19), T.FechaAlta, 120)     AS fecha_alta,
    CONVERT(VARCHAR(19), T.FechaOrden, 120)    AS fecha_orden,
    CONVERT(VARCHAR(19), T.FechaLista, 120)    AS fecha_lista,
    CONVERT(VARCHAR(19), T.FechaCerrada, 120)  AS fecha_cerrada,
    ISNULL(CAST(T.Responsable AS VARCHAR(20)), '') AS responsable,
    ISNULL(CAST(T.IDPolitica AS VARCHAR(20)), '')  AS id_politica,
    CAST(T.CostoTotal AS VARCHAR(30))         AS costo_total,
    CAST(T.VentaTotal AS VARCHAR(30))         AS venta_total,
    CAST(ISNULL(T.TotalPresupuesto, 0) AS VARCHAR(30)) AS total_presupuesto,
    ISNULL(REPLACE(REPLACE(REPLACE(T.Ubicacion, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS ubicacion,
    ISNULL(REPLACE(REPLACE(REPLACE(T.Comprobante, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS comprobante,
    ISNULL(REPLACE(REPLACE(REPLACE(T.FacturaEmitida, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS factura_emitida,
    REPLACE(REPLACE(REPLACE(ISNULL(T.TrabajoRealizado, N''), NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS trabajo_realizado,
    CAST(ISNULL(T.Liquidada, 0) AS VARCHAR(5)) AS liquidada,
    ISNULL(CAST(T.Garantia AS VARCHAR(5)), '') AS garantia,
    ISNULL(CAST(T.LiquidacionNro AS VARCHAR(20)), '') AS liquidacion_nro
FROM dbo.CS_Trabajos T
WHERE T.FechaAlta >= '20200101'
ORDER BY T.IDTrabajo;
