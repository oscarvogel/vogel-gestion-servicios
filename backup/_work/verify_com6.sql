SET NOCOUNT ON;

PRINT '=== Formula (venta-costo)*cantidad*pct/100 vs ComisionServicios guardado ===';
SELECT TOP 12
  T.IDTrabajo, PR.Item, PR.Tipo, PR.Cantidad,
  CAST(PR.Unitario AS DECIMAL(19,6)) AS unitario,
  CAST(PR.CostoUnitario AS DECIMAL(19,6)) AS costo_unitario,
  PR.LiquidaComision, PR.Provee,
  POL.ComisionServ AS modo, POL.MontoComisionServ AS pct,
  ROUND((CAST(PR.Unitario AS DECIMAL(19,6)) - CAST(PR.CostoUnitario AS DECIMAL(19,6))) * PR.Cantidad * POL.MontoComisionServ / 100.0, 2) AS calculado,
  CAST(PR.CostoComision AS DECIMAL(19,6)) AS guardado
FROM dbo.CS_Partes PR
JOIN dbo.CS_Trabajos T ON T.IDTrabajo = PR.NroOrden
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
WHERE PR.Tipo = 2 AND PR.LiquidaComision > 0 AND PR.CostoComision IS NOT NULL
ORDER BY PR.ID DESC;

PRINT '';
PRINT '=== CASO CON COSTO > 0 (la diferencia clave) ===';
SELECT TOP 10
  T.IDTrabajo, PR.Item, PR.Tipo, PR.Cantidad,
  CAST(PR.Unitario AS DECIMAL(19,6)) AS unitario,
  CAST(PR.CostoUnitario AS DECIMAL(19,6)) AS costo_unitario,
  PR.LiquidaComision, POL.MontoComisionServ AS pct,
  ROUND((CAST(PR.Unitario AS DECIMAL(19,6)) - CAST(PR.CostoUnitario AS DECIMAL(19,6))) * PR.Cantidad * POL.MontoComisionServ / 100.0, 2) AS calculado,
  CAST(PR.CostoComision AS DECIMAL(19,6)) AS guardado,
  ROUND(CAST(PR.CostoComision AS DECIMAL(19,6)) - ROUND((CAST(PR.Unitario AS DECIMAL(19,6)) - CAST(PR.CostoUnitario AS DECIMAL(19,6))) * PR.Cantidad * POL.MontoComisionServ / 100.0, 2), 2) AS diferencia
FROM dbo.CS_Partes PR
JOIN dbo.CS_Trabajos T ON T.IDTrabajo = PR.NroOrden
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
WHERE PR.Tipo = 2 AND PR.LiquidaComision > 0 AND PR.CostoComision IS NOT NULL
  AND PR.CostoUnitario > 0
ORDER BY PR.ID DESC;

PRINT '';
PRINT '=== Coherencia global de la formula ===';
SELECT COUNT(*) AS lineas,
       SUM(CASE WHEN ABS(CAST(PR.CostoComision AS DECIMAL(19,6)) -
           ROUND((CAST(PR.Unitario AS DECIMAL(19,6)) - CAST(PR.CostoUnitario AS DECIMAL(19,6))) * PR.Cantidad * POL.MontoComisionServ / 100.0, 2)) <= 1 THEN 1 ELSE 0 END) AS coinciden
FROM dbo.CS_Partes PR
JOIN dbo.CS_Trabajos T ON T.IDTrabajo = PR.NroOrden
JOIN dbo.CS_PoliticasxArea POL ON POL.ID = T.IDPolitica
WHERE PR.Tipo = 2 AND PR.LiquidaComision > 0 AND PR.CostoComision IS NOT NULL;

PRINT '';
PRINT '=== Tablas de liquidacion que faltaban ===';
SELECT 'Liquidaciones' AS t, COUNT(*) AS n FROM dbo.Liquidaciones
UNION ALL SELECT 'OrdenesLiquidadas', COUNT(*) FROM dbo.OrdenesLiquidadas
UNION ALL SELECT 'CS_Partes', COUNT(*) FROM dbo.CS_Partes
UNION ALL SELECT 'CS_EscalasDescuentosEsquema', COUNT(*) FROM dbo.CS_EscalasDescuentosEsquema
UNION ALL SELECT 'CC_Comisiones', COUNT(*) FROM dbo.CC_Comisiones
UNION ALL SELECT 'CC_EsquemasComision', COUNT(*) FROM dbo.CC_EsquemasComision
UNION ALL SELECT 'CC_Comisiones_Historico', COUNT(*) FROM dbo.CC_Comisiones_Historico;
