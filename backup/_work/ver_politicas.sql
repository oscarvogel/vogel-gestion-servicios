SET NOCOUNT ON;

SELECT 'POLICY';
SELECT 'P|' + CAST(AUX.ID AS VARCHAR(20)) + '|area=' + CAST(AUX.Area AS VARCHAR(20))
     + '|tipo=' + ISNULL(AUX.TipoTrabajo,'(null)')
     + '|Area=' + A.Area
     + '|CodCli=' + ISNULL(CAST(A.CodCli AS VARCHAR(20)),'NULL')
     + '|Cli=' + ISNULL(CC.Cliente,'(null)')
     + '|Gt=' + ISNULL(CAST(ISNULL(TT.Garantia, A.GarantiasTerceros) AS VARCHAR(5)),'NULL')
     + '|Liq=' + ISNULL(CAST(COALESCE(TT.Liquidacion, A.Liquidar) AS VARCHAR(5)),'NULL')
     + '|Util=' + ISNULL(CAST(ISNULL(TT.Utilidad,0) AS VARCHAR(5)),'NULL')
     + '|Desc=' + ISNULL(TT.Descripcion,'(null)')
FROM dbo.Aux_PoliticasxArea AUX
JOIN dbo.Areas A ON A.Codigo = AUX.Area
LEFT JOIN dbo.TiposTrabajos TT ON TT.Area = AUX.Area AND TT.Codigo = AUX.TipoTrabajo
LEFT JOIN dbo.CC_Clientes_Tabla CC ON CC.CodCli = A.CodCli
ORDER BY A.Area, AUX.TipoTrabajo;

SELECT 'VOL2020';
SELECT 'V|area=' + CAST(AUX.Area AS VARCHAR(20)) + '|tipo=' + ISNULL(AUX.TipoTrabajo,'(null)')
     + '|Area=' + A.Area
     + '|Cli=' + ISNULL(CC.Cliente,'(null)')
     + '|CodCli=' + ISNULL(CAST(A.CodCli AS VARCHAR(20)),'NULL')
     + '|ots=' + CAST(COUNT(*) AS VARCHAR(20))
     + '|e8=' + CAST(SUM(CASE WHEN T.Estado = 8 THEN 1 ELSE 0 END) AS VARCHAR(20))
     + '|venta=' + CAST(ISNULL(SUM(T.VentaTotal),0) AS VARCHAR(30))
     + '|costo=' + CAST(ISNULL(SUM(T.CostoTotal),0) AS VARCHAR(30))
FROM dbo.CS_Trabajos T
JOIN dbo.Aux_PoliticasxArea AUX ON AUX.ID = T.IDPolitica
JOIN dbo.Areas A ON A.Codigo = AUX.Area
LEFT JOIN dbo.CC_Clientes_Tabla CC ON CC.CodCli = A.CodCli
WHERE T.FechaAlta >= '20200101'
GROUP BY AUX.Area, AUX.TipoTrabajo, A.Area, A.CodCli, CC.Cliente
ORDER BY A.Area, AUX.TipoTrabajo;
