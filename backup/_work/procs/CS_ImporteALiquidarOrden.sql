

CREATE   FUNCTION CS_ImporteALiquidarOrden(@IDTrabajo INT)
RETURNS DECIMAL(19, 5)
AS
BEGIN
	DECLARE @Utilidad int
	DECLARE @Facturacion0 bit
	DECLARE @Facturacion1 bit
	DECLARE @Facturacion2 bit
	DECLARE @Facturacion3 bit
	DECLARE @Importe DECIMAL(19, 5)

	SET @Facturacion0 = 0
	SET @Facturacion1 = 0
	SET @Facturacion2 = 0
	SET @Facturacion3 = 0

      	SELECT @Utilidad = P.Utilidad FROM CS_PoliticasxArea P INNER JOIN CS_Trabajos T ON T.IDPolitica = P.ID WHERE T.IDTrabajo = @IDTrabajo
	IF @Utilidad = 0 Or @Utilidad = 3 SET @Facturacion0 = 1
	SET @Facturacion1 = @Facturacion0
	IF @Utilidad = 0 Or @Utilidad = 2 SET @Facturacion2 = 1
	IF @Utilidad <> 1 SET @Facturacion3 = 1


	SELECT @Importe = SUM(COALESCE(Unitario, 0) * COALESCE(Cantidad, 1)) FROM Partes
	WHERE NroOrden = @IDTrabajo AND (  (Partes.Tipo = 0 AND @Facturacion0 = 1 ) 
					OR (Partes.Tipo = 1 AND @Facturacion1 = 1 ) 	
					OR (Partes.Tipo = 2 AND @Facturacion2 = 1 ) 	
					OR (Partes.Tipo = 3 AND @Facturacion3 = 1 ) 	
					)
	RETURN COALESCE(@Importe, 0)
END
		









(1 rows affected)
