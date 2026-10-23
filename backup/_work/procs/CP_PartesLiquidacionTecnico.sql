CREATE PROCEDURE [dbo].[CP_PartesLiquidacionTecnico]
@IDLiquidacion INT
AS
SELECT ID, Tipo, NumeroParte, Descripcion, Sum(Cantidad) as Cantidad, Comision/Cantidad as Unitario, Moneda 
FROM CP_ItemsLiquidacionTecnico 
WHERE Liquidacion = @IDLiquidacion
GROUP BY ID, Tipo, NumeroParte, Descripcion, Comision/Cantidad, Moneda 


(1 rows affected)
