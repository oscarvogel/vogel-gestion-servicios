SET NOCOUNT ON;
-- Politicas = dbo.CS_PoliticasxArea (la vista que une dbo.Areas + dbo.TiposTrabajos
-- + dbo.Aux_PoliticasxArea). P.ID es el Aux.ID, o sea el mismo ID que guarda
-- dbo.CS_Trabajos.IDPolitica.
-- Se elige la vista y no las tablas a mano porque la vista ya resuelve Garantia y Liquidar
-- con la regla real del legacy (principal vs sub-tipo).
SELECT
    CAST(P.ID AS VARCHAR(20))                AS policy_id,
    CAST(P.IDArea AS VARCHAR(20))            AS area_code,
    REPLACE(REPLACE(REPLACE(P.Area, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS area_name,
    CASE WHEN P.Ppal = 1 THEN N'' ELSE ISNULL(P.Codigo, N'') END AS policy_code,
    CASE WHEN P.Ppal = 1 THEN N'' ELSE ISNULL(REPLACE(REPLACE(REPLACE(P.Nombre, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), N'') END AS policy_description,
    ISNULL(CAST(P.CodCli AS VARCHAR(20)), '') AS billing_codcli,
    ISNULL(REPLACE(REPLACE(REPLACE(P.Empresa, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS brand_name,
    CAST(P.Garantia AS VARCHAR(5))           AS warranty_type,
    CAST(P.Liquidar AS VARCHAR(5))           AS liquidate_mode,
    CAST(P.Utilidad AS VARCHAR(5))           AS utility,
    ISNULL(CAST(P.ComisionProd AS VARCHAR(10)), '')   AS comision_prod_mode,
    ISNULL(CAST(P.MontoComisionProd AS VARCHAR(30)), '') AS comision_prod_pct,
    ISNULL(CAST(P.ComisionRep AS VARCHAR(10)), '')    AS comision_part_mode,
    ISNULL(CAST(P.MontoComisionRep AS VARCHAR(30)), '') AS comision_part_pct,
    ISNULL(CAST(P.ComisionServ AS VARCHAR(10)), '')   AS comision_service_mode,
    ISNULL(CAST(P.MontoComisionServ AS VARCHAR(30)), '') AS comision_service_pct,
    ISNULL(CAST(P.ComisionOtro AS VARCHAR(10)), '')   AS comision_other_mode,
    ISNULL(CAST(P.MontoComisionOtro AS VARCHAR(30)), '') AS comision_other_pct
FROM dbo.CS_PoliticasxArea P
ORDER BY P.IDArea, P.Ppal DESC;
