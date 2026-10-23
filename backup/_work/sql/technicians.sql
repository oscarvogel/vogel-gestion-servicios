SET NOCOUNT ON;
-- Quien intervino en las OTs del corte y cuanto se le comisiona (dbo.Intervienen).
-- El importe de la comision YA esta calculado por el legacy: se migra tal cual, no se recalcula.
-- Persona es el Codigo de dbo.CC_Usuarios. 40 de las 77 personas que intervinieron ya no
-- existen como usuario: el legacy las muestra como "Sistema".
SELECT
    CAST(I.Orden AS VARCHAR(20))               AS orden,
    CAST(I.Persona AS VARCHAR(20))             AS persona,
    CAST(ISNULL(I.ComisionProductos, 0) AS VARCHAR(30)) AS comision_productos,
    CAST(ISNULL(I.ComisionPartes, 0) AS VARCHAR(30))    AS comision_partes,
    CAST(ISNULL(I.ComisionServicios, 0) AS VARCHAR(30)) AS comision_servicios,
    CAST(ISNULL(I.ComisionOtros, 0) AS VARCHAR(30))     AS comision_otros,
    ISNULL(CAST(I.Liquidacion AS VARCHAR(20)), '')      AS liquidacion,
    CONVERT(VARCHAR(19), ISNULL(I.FechaLiquidacionTecnico, '1900-01-01'), 120) AS fecha_liquidacion,
    ISNULL(REPLACE(REPLACE(REPLACE(I.NroFactura, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS nro_factura
FROM dbo.Intervienen I
INNER JOIN dbo.CS_Trabajos T ON T.IDTrabajo = I.Orden
WHERE T.FechaAlta >= '20200101'
ORDER BY I.Orden, I.Persona;
