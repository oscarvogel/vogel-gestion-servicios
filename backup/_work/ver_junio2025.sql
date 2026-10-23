SET NOCOUNT ON;

SELECT 'JUNIO_2025_TOTAL';
SELECT 'A|gt=' + CAST(ISNULL(TT.Garantia, A.GarantiasTerceros) AS VARCHAR(5))
     + '|conEmpresa=' + CAST(SUM(CASE WHEN A.CodCli <> 0 THEN 1 ELSE 0 END) AS VARCHAR(20))
     + '|ots=' + CAST(COUNT(*) AS VARCHAR(20))
     + '|costo=' + CAST(ISNULL(SUM(T.CostoTotal),0) AS VARCHAR(30))
FROM dbo.CS_Trabajos T
JOIN dbo.Aux_PoliticasxArea AUX ON AUX.ID = T.IDPolitica
JOIN dbo.Areas A ON A.Codigo = AUX.Area
LEFT JOIN dbo.TiposTrabajos TT ON TT.Area = AUX.Area AND TT.Codigo = AUX.TipoTrabajo
WHERE T.FechaLista >= '20250601' AND T.FechaLista < '20250701'
GROUP BY ISNULL(TT.Garantia, A.GarantiasTerceros);

SELECT 'JUNIO_2025_GT1_TOTAL';
SELECT 'B|ots=' + CAST(COUNT(*) AS VARCHAR(20))
     + '|costo=' + CAST(ISNULL(SUM(T.CostoTotal),0) AS VARCHAR(30))
FROM dbo.CS_Trabajos T
JOIN dbo.Aux_PoliticasxArea AUX ON AUX.ID = T.IDPolitica
JOIN dbo.Areas A ON A.Codigo = AUX.Area
LEFT JOIN dbo.TiposTrabajos TT ON TT.Area = AUX.Area AND TT.Codigo = AUX.TipoTrabajo
WHERE T.FechaLista >= '20250601' AND T.FechaLista < '20250701'
  AND ISNULL(TT.Garantia, A.GarantiasTerceros) = 1 AND A.CodCli <> 0;

SELECT 'JUNIO_2025_TODAS_CON_EMPRESA';
SELECT 'C|ots=' + CAST(COUNT(*) AS VARCHAR(20))
     + '|costo=' + CAST(ISNULL(SUM(T.CostoTotal),0) AS VARCHAR(30))
FROM dbo.CS_Trabajos T
JOIN dbo.Aux_PoliticasxArea AUX ON AUX.ID = T.IDPolitica
JOIN dbo.Areas A ON A.Codigo = AUX.Area
WHERE T.FechaLista >= '20250601' AND T.FechaLista < '20250701' AND A.CodCli <> 0;
