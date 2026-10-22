SET NOCOUNT ON;
-- Facturas del legacy (dbo.CG_Facturas_Tabla) que se pueden vincular a una OT.
--
-- La tabla de facturas termina el 2021-06-30. Despues, el numero de factura paso a
-- dbo.CS_Trabajos.Comprobante, con formato 0006-00023033, que NO existe en esta tabla.
-- Y dbo.CS_Trabajos.FacturaEmitida, en las OTs viejas, si coincide con Numero.
-- De ahi el LEFT JOIN: solo las facturas que una OT claims.
--
-- TipoDoc: 1 = Factura, 31 = FCE MiPyme. La clave real es (TipoDoc, Numero).
-- La fecha es Fecha (NO FechaComprobante: coinciden 1 de 3.494).
SELECT
    CAST(F.ID AS VARCHAR(20))              AS id_factura,
    REPLACE(REPLACE(REPLACE(F.Numero, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS numero,
    CAST(F.TipoDoc AS VARCHAR(5))          AS tipo_doc,
    CAST(F.CodCli AS VARCHAR(20))          AS codcli,
    REPLACE(REPLACE(REPLACE(ISNULL(F.Cliente, N''), NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS cliente,
    CONVERT(VARCHAR(19), F.Fecha, 120)     AS fecha,
    CONVERT(VARCHAR(19), F.Vencimiento, 120) AS vencimiento,
    CAST(F.Bruto AS VARCHAR(30))           AS bruto,
    CAST(F.Neto AS VARCHAR(30))            AS neto,
    CAST(F.Total AS VARCHAR(30))           AS total,
    ISNULL(F.CUIT, '')                     AS cuit,
    ISNULL(CAST(F.Vendedor AS VARCHAR(20)), '') AS vendedor,
    ISNULL(CAST(F.RealizadoPor AS VARCHAR(20)), '') AS realizado_por,
    CAST(ISNULL(F.Anulado, 0) AS VARCHAR(5)) AS anulado,
    ISNULL(F.CAI, '')                      AS cai,
    ISNULL(CAST((SELECT MIN(T.IDTrabajo) FROM dbo.CS_Trabajos T WHERE T.FacturaEmitida = F.Numero) AS VARCHAR(20)), '') AS id_trabajo
FROM dbo.CG_Facturas_Tabla F
ORDER BY F.ID;
