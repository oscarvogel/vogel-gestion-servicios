SET NOCOUNT ON;

PRINT '=== A. CONFIGURACION DE COMISION POR AREA (CS_PoliticasxArea) ===';
SELECT P.ID, P.IDArea, P.Codigo, P.Nombre, P.Empresa, P.Garantia, P.Liquidar, P.Utilidad,
       P.Comision, P.ComisionProd, P.MontoComisionProd, P.ComisionRep, P.MontoComisionRep,
       P.ComisionServ, P.MontoComisionServ, P.ComisionOtro, P.MontoComisionOtro,
       P.ComisionValor, P.MontoComisionValor,
       P.MomentoAutorizacion, P.MontoAutorizar, P.MomentoComprobante, P.MomentoInformar,
       P.ExcluirdeFactura, P.ExigirComprobante, P.TrabajoPredeterminado, P.CodCli
FROM dbo.CS_PoliticasxArea P
ORDER BY P.ID;
