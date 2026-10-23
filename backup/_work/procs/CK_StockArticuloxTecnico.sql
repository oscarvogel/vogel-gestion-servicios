CREATE  PROCEDURE [dbo].[CK_StockArticuloxTecnico]
@in_Tecnico int,
@in_ID int,
@Stock real output 
as
SELECT @Stock = COALESCE(Stock,0) + COALESCE(EnTransito,0)
FROM CK_ArticulosxDeposito WHERE IDDeposito = -@in_Tecnico AND IDArticulo = @in_ID



(1 rows affected)
