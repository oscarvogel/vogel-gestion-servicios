SET NOCOUNT ON;
-- Lineas de las OTs del corte 2020+ (dbo.CS_Partes).
-- Unitario = precio de venta al cliente final; CostoUnitario = costo real.
-- En garantia de terceros el legacy infla el precio (@Unitario = @Costo * (1 + @PorcUtil/100)),
-- por eso VentaTotal sale aproximadamente el doble que CostoTotal.
-- LiquidaComision: 0 sin comision, -1 todos, -2 responsable, -3 proveedor, >0 codigo de tecnico.
SELECT
    CAST(P.NroOrden AS VARCHAR(20))            AS nro_orden,
    CAST(P.Item AS VARCHAR(20))                AS item,
    ISNULL(REPLACE(REPLACE(REPLACE(P.NumeroParte, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS numero_parte,
    CAST(P.Cantidad AS VARCHAR(30))            AS cantidad,
    REPLACE(REPLACE(REPLACE(ISNULL(P.Descripcion, N''), NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS descripcion,
    CAST(P.CostoUnitario AS VARCHAR(30))       AS costo_unitario,
    CAST(P.Unitario AS VARCHAR(30))            AS unitario,
    CAST(P.Tipo AS VARCHAR(5))                 AS tipo,
    ISNULL(CAST(P.LiquidaComision AS VARCHAR(20)), '0') AS liquida_comision,
    ISNULL(CAST(P.Cotizacion AS VARCHAR(20)), '') AS cotizacion,
    ISNULL(CAST(P.CotizacionCosto AS VARCHAR(20)), '') AS cotizacion_costo,
    ISNULL(CAST(P.Provee AS VARCHAR(20)), '')  AS provee,
    CAST(P.ID AS VARCHAR(20))                  AS id_parte
FROM dbo.CS_Partes P
INNER JOIN dbo.CS_Trabajos T ON T.IDTrabajo = P.NroOrden
WHERE T.FechaAlta >= '20200101'
ORDER BY P.NroOrden, P.Item;
