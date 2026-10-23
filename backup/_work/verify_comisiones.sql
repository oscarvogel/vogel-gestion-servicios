SET NOCOUNT ON;

PRINT '=== 1. CS_PoliticasxArea: esquema y Utilidad ===';
SELECT c.name, ty.name, c.max_length, c.is_nullable FROM sys.columns c
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id = OBJECT_ID(N'dbo.CS_PoliticasxArea') ORDER BY c.column_id;
SELECT COUNT(*) AS filas FROM dbo.CS_PoliticasxArea;
SELECT Utilidad, COUNT(*) AS n FROM dbo.CS_PoliticasxArea GROUP BY Utilidad ORDER BY n DESC;

PRINT '';
PRINT '=== 2. Join: Area <-> TipoTrabajo <-> Utilidad ===';
SELECT TOP 30 P.ID, P.Area, A.TipoTrabajo, P.Utilidad
FROM dbo.CS_PoliticasxArea P
LEFT JOIN dbo.Aux_PoliticasxArea A ON A.ID = P.ID
ORDER BY P.ID;

PRINT '';
PRINT '=== 3. Como se usa Utilidad en la comision: efecto en el importe liquidable ===';
SELECT P.Utilidad,
       COUNT(DISTINCT T.IDTrabajo) AS trabajos_con_esa_utilidad,
       SUM(CASE WHEN T.Garantia = 1 THEN 1 ELSE 0 END) AS en_garantia,
       SUM(CASE WHEN T.Garantia = 0 THEN 1 ELSE 0 END) AS fuera_garantia
FROM dbo.CS_PoliticasxArea P
JOIN dbo.CS_Trabajos T ON T.IDPolitica = P.ID
GROUP BY P.Utilidad ORDER BY P.Utilidad;

PRINT '';
PRINT '=== 4. CC_EsquemasComision: cuantos esquemas hay ===';
SELECT COUNT(*) AS esquemas FROM dbo.CC_EsquemasComision;
SELECT TOP 15 * FROM dbo.CC_EsquemasComision ORDER BY 1;

PRINT '';
PRINT '=== 5. CC_Comisiones (actual) vs historico ===';
SELECT COUNT(*) AS cc_comisiones_actuales FROM dbo.CC_Comisiones;
SELECT COUNT(*) AS cc_comisiones_historico FROM dbo.CC_Comisiones_Historico;

PRINT '';
PRINT '=== 6. La vista Partes (base del importe liquidable) ===';
SELECT c.name, ty.name, c.max_length FROM sys.columns c
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id = OBJECT_ID(N'dbo.Partes') ORDER BY c.column_id;

PRINT '';
PRINT '=== 7. Tipos de Parte: distribucion real ===';
SELECT Tipo, COUNT(*) AS n, SUM(CASE WHEN Tipo = 0 THEN 1 ELSE 0 END) AS repuestos,
       SUM(CASE WHEN Tipo = 2 THEN 1 ELSE 0 END) AS servicios
FROM dbo.CS_Partes GROUP BY Tipo ORDER BY Tipo;

PRINT '';
PRINT '=== 8. Coherencia de la liquidacion: ejemplo real de una OT liquidada ===';
SELECT TOP 6 T.IDTrabajo, T.NumeroOrden, T.Estado, T.VentaTotal, T.CostoTotal,
       T.VentaTotalComisiones, T.CostoTotalComisiones, T.Liquidada, T.FechaLiquidacion, T.LiquidacionNro,
       I.Persona, I.ComisionServicios, I.ComisionPartes, I.Liquidacion AS liq_tecnico, I.NroFactura
FROM dbo.CS_Trabajos T
JOIN dbo.Intervienen I ON I.Orden = T.IDTrabajo
WHERE T.Liquidada = 1 AND T.FechaLiquidacion IS NOT NULL
ORDER BY T.FechaLiquidacion DESC;
