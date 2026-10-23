SET NOCOUNT ON;

SELECT 'RESUMEN_EMPRESA_TIPO';
SELECT 'R|' + ISNULL(CC.Cliente,'(SIN EMPRESA: CodCli=0)') + '|CodCli=' + ISNULL(CAST(A.CodCli AS VARCHAR(20)),'NULL')
     + '|gt=' + CAST(ISNULL(TT.Garantia, A.GarantiasTerceros) AS VARCHAR(5))
     + '|liq=' + CAST(COALESCE(TT.Liquidacion, A.Liquidar) AS VARCHAR(5))
     + '|ots=' + CAST(COUNT(*) AS VARCHAR(20))
     + '|e8=' + CAST(SUM(CASE WHEN T.Estado = 8 THEN 1 ELSE 0 END) AS VARCHAR(20))
     + '|venta=' + CAST(ISNULL(SUM(T.VentaTotal),0) AS VARCHAR(30))
     + '|costo=' + CAST(ISNULL(SUM(T.CostoTotal),0) AS VARCHAR(30))
FROM dbo.CS_Trabajos T
JOIN dbo.Aux_PoliticasxArea AUX ON AUX.ID = T.IDPolitica
JOIN dbo.Areas A ON A.Codigo = AUX.Area
LEFT JOIN dbo.TiposTrabajos TT ON TT.Area = AUX.Area AND TT.Codigo = AUX.TipoTrabajo
LEFT JOIN dbo.CC_Clientes_Tabla CC ON CC.CodCli = A.CodCli
WHERE T.FechaAlta >= '20200101'
GROUP BY CC.Cliente, A.CodCli, ISNULL(TT.Garantia, A.GarantiasTerceros), COALESCE(TT.Liquidacion, A.Liquidar)
ORDER BY ISNULL(CC.Cliente,'zzz'), ISNULL(TT.Garantia, A.GarantiasTerceros);

SELECT 'TOTAL_POR_BUCKET';
SELECT 'T|gt=' + CAST(ISNULL(TT.Garantia, A.GarantiasTerceros) AS VARCHAR(5))
     + '|conEmpresa=' + CAST(SUM(CASE WHEN A.CodCli <> 0 THEN 1 ELSE 0 END) AS VARCHAR(20))
     + '|ots=' + CAST(COUNT(*) AS VARCHAR(20))
     + '|venta=' + CAST(ISNULL(SUM(T.VentaTotal),0) AS VARCHAR(30))
     + '|costo=' + CAST(ISNULL(SUM(T.CostoTotal),0) AS VARCHAR(30))
FROM dbo.CS_Trabajos T
JOIN dbo.Aux_PoliticasxArea AUX ON AUX.ID = T.IDPolitica
JOIN dbo.Areas A ON A.Codigo = AUX.Area
LEFT JOIN dbo.TiposTrabajos TT ON TT.Area = AUX.Area AND TT.Codigo = AUX.TipoTrabajo
WHERE T.FechaAlta >= '20200101'
GROUP BY ISNULL(TT.Garantia, A.GarantiasTerceros);

SELECT 'TOTAL_EMPRESAS';
SELECT 'E|ots=' + CAST(COUNT(*) AS VARCHAR(20))
     + '|venta=' + CAST(ISNULL(SUM(T.VentaTotal),0) AS VARCHAR(30))
     + '|costo=' + CAST(ISNULL(SUM(T.CostoTotal),0) AS VARCHAR(30))
FROM dbo.CS_Trabajos T
JOIN dbo.Aux_PoliticasxArea AUX ON AUX.ID = T.IDPolitica
JOIN dbo.Areas A ON A.Codigo = AUX.Area
WHERE T.FechaAlta >= '20200101' AND A.CodCli <> 0;

SELECT 'MESES_EJEMPLO_2025';
SELECT 'M|' + CONVERT(CHAR(7), T.FechaLista, 126) + '|Cli=' + ISNULL(CC.Cliente,'(SIN EMPRESA)')
     + '|gt=' + CAST(ISNULL(TT.Garantia, A.GarantiasTerceros) AS VARCHAR(5))
     + '|ots=' + CAST(COUNT(*) AS VARCHAR(20))
     + '|costo=' + CAST(ISNULL(SUM(T.CostoTotal),0) AS VARCHAR(30))
FROM dbo.CS_Trabajos T
JOIN dbo.Aux_PoliticasxArea AUX ON AUX.ID = T.IDPolitica
JOIN dbo.Areas A ON A.Codigo = AUX.Area
LEFT JOIN dbo.TiposTrabajos TT ON TT.Area = AUX.Area AND TT.Codigo = AUX.TipoTrabajo
LEFT JOIN dbo.CC_Clientes_Tabla CC ON CC.CodCli = A.CodCli
WHERE T.FechaLista >= '20250601' AND T.FechaLista < '20250701'
GROUP BY CONVERT(CHAR(7), T.FechaLista, 126), CC.Cliente, ISNULL(TT.Garantia, A.GarantiasTerceros)
ORDER BY CONVERT(CHAR(7), T.FechaLista, 126), CC.Cliente, ISNULL(TT.Garantia, A.GarantiasTerceros);
