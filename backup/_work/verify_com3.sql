SET NOCOUNT ON;

PRINT '=== 1. Distribucion Liquidar / Garantia / Utilidad por area ===';
SELECT P.Liquidar, P.Garantia, P.Utilidad, COUNT(*) AS n,
       SUM(CASE WHEN P.ComisionServ > 0 THEN 1 ELSE 0 END) AS con_comision_serv,
       MIN(P.MontoComisionServ) AS monto_serv_min, MAX(P.MontoComisionServ) AS monto_serv_max
FROM dbo.CS_PoliticasxArea P
GROUP BY P.Liquidar, P.Garantia, P.Utilidad ORDER BY P.Liquidar, P.Garantia;

PRINT '';
PRINT '=== 2. VALIDACION DEL 50%: ComisionServicios vs 50% del importe liquidable ===';
-- Para una muestra de OTs, comparamos ComisionServicios con el importe a liquidar.
WITH muestra AS (
  SELECT TOP 15 T.IDTrabajo, T.VentaTotal, T.CostoTotal, T.VentaTotalComisiones, T.CostoTotalComisiones,
         I.Persona, I.ComisionServicios, I.ComisionPartes, I.ComisionProductos,
         dbo.CS_ImporteALiquidarOrden(T.IDTrabajo) AS importe_a_liquidar,
         P.Liquidar, P.Garantia, P.MontoComisionServ, T.Liquidada, T.FechaLiquidacion
  FROM dbo.CS_Trabajos T
  JOIN dbo.Intervienen I ON I.Orden = T.IDTrabajo
  JOIN dbo.CS_PoliticasxArea P ON P.ID = T.IDPolitica
  WHERE T.Estado = 8 AND I.ComisionServicios <> 0
  ORDER BY T.IDTrabajo DESC
)
SELECT IDTrabajo, Persona, Garantia, Liquidar, MontoComisionServ, ComisionServicios,
       Importe_a_liquidar, ROUND(Importe_a_liquidar * MontoComisionServ / 100.0, 2) AS esperado_50,
       Liquidada, FechaLiquidacion
FROM muestra;

PRINT '';
PRINT '=== 3. Coherencia global: ComisionServicios == importe_liquidable * monto/100 ? ===';
SELECT COUNT(*) AS filas,
       SUM(CASE WHEN ROUND(dbo.CS_ImporteALiquidarOrden(T.IDTrabajo) * P.MontoComisionServ / 100.0, 2)
                     = ROUND(I.ComisionServicios, 2) THEN 1 ELSE 0 END) AS coinciden,
       SUM(CASE WHEN I.ComisionServicios = 0 THEN 1 ELSE 0 END) AS comision_serv_cero
FROM dbo.CS_Trabajos T
JOIN dbo.Intervienen I ON I.Orden = T.IDTrabajo
JOIN dbo.CS_PoliticasxArea P ON P.ID = T.IDPolitica
WHERE T.Estado = 8;

PRINT '';
PRINT '=== 4. GARANTIA vs Liquidacion: las OT en garantia se liquidan? ===';
SELECT P.Garantia, P.Liquidar, COUNT(DISTINCT T.IDTrabajo) AS ots,
       SUM(CASE WHEN T.Liquidada = 1 THEN 1 ELSE 0 END) AS liquidadas,
       SUM(CASE WHEN I.ComisionServicios <> 0 THEN 1 ELSE 0 END) AS con_comision_serv
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea P ON P.ID = T.IDPolitica
LEFT JOIN dbo.Intervienen I ON I.Orden = T.IDTrabajo
WHERE T.Estado = 8
GROUP BY P.Garantia, P.Liquidar ORDER BY P.Garantia, P.Liquidar;

PRINT '';
PRINT '=== 5. ejemplo: OT en garantia con comision (deberia ser 0) ===';
SELECT TOP 6 T.IDTrabajo, T.Estado, T.Garantia AS garantia_ot, P.Garantia AS garantia_area, P.Liquidar,
       I.Persona, I.ComisionServicios, T.Liquidada, T.VentaTotal, T.VentaTotalComisiones
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea P ON P.ID = T.IDPolitica
JOIN dbo.Intervienen I ON I.Orden = T.IDTrabajo
WHERE T.Estado = 8 AND P.Garantia = 1 AND I.ComisionServicios <> 0;

PRINT '';
PRINT '=== 6. ejemplo: OT fuera de garantia con comision ===';
SELECT TOP 6 T.IDTrabajo, T.Estado, T.Garantia AS garantia_ot, P.Garantia AS garantia_area, P.Liquidar,
       I.Persona, I.ComisionServicios, I.ComisionPartes, T.Liquidada, T.VentaTotal, T.VentaTotalComisiones
FROM dbo.CS_Trabajos T
JOIN dbo.CS_PoliticasxArea P ON P.ID = T.IDPolitica
JOIN dbo.Intervienen I ON I.Orden = T.IDTrabajo
WHERE T.Estado = 8 AND P.Garantia = 0 AND I.ComisionServicios <> 0
ORDER BY T.IDTrabajo DESC;
