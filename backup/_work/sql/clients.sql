SET NOCOUNT ON;
-- Clientes del legacy (dbo.CC_Clientes_Tabla) + el CUIT mas frecuente de sus facturas.
-- El CUIT solo se toma si tiene 11 digitos: en la base hay placeholders como '100000'
-- (6 digitos) y '11111111' (8) que no son CUIT.
WITH cuit AS (
    SELECT F.CodCli,
           F.CUIT,
           ROW_NUMBER() OVER (PARTITION BY F.CodCli ORDER BY COUNT(*) DESC, F.CUIT) AS rn
    FROM dbo.CG_Facturas_Tabla F
    WHERE LEN(F.CUIT) = 11 AND F.CUIT NOT LIKE '%[^0-9]%'
    GROUP BY F.CodCli, F.CUIT
)
SELECT
    CAST(C.CodCli AS VARCHAR(20))            AS codcli,
    REPLACE(REPLACE(REPLACE(C.Cliente, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS cliente,
    ISNULL(REPLACE(REPLACE(REPLACE(C.Telefonos, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS telefonos,
    ISNULL(REPLACE(REPLACE(REPLACE(C.Email, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS email,
    ISNULL(CAST(C.Vendedor AS VARCHAR(20)), '') AS vendedor,
    ISNULL(CAST(C.Tipo AS VARCHAR(20)), '')     AS tipo,
    REPLACE(REPLACE(REPLACE(
        ISNULL(C.Calle, N'') + N' ' + ISNULL(CAST(C.Altura AS VARCHAR(20)), N'') + N', ' +
        ISNULL(C.Localidad, N'') + N' (' + ISNULL(C.CodigoPostal, N'') + N')' +
        CASE WHEN ISNULL(C.Partido, N'') <> N'' THEN N' - ' + C.Partido ELSE N'' END,
        NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS direccion,
    ISNULL(REPLACE(REPLACE(REPLACE(C.NuestroCodigo, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS nuestro_codigo,
    ISNULL(CAST(C.Liquidar AS VARCHAR(5)), '0') AS liquidar_cliente,
    ISNULL(CU.CUIT, '') AS cuit
FROM dbo.CC_Clientes_Tabla C
LEFT JOIN cuit CU ON CU.CodCli = C.CodCli AND CU.rn = 1
ORDER BY C.CodCli;
