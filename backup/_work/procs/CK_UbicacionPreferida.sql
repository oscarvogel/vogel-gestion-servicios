CREATE FUNCTION CK_UbicacionPreferida (@IDDeposito INT, @IDArticulo INT, @Cantidad Decimal(19,5),  @Modo TINYINT)
RETURNS  INT
AS
BEGIN
	-- Modo --> 0=Liberar Espacio 1=Optimizar Recorrido
	DECLARE @ManejaUbicaciones BIT
	DECLARE @IDUbicacion INT
	SELECT @ManejaUbicaciones = COALESCE(ManejaUbicaciones, 0) FROM CK_Depositos WHERE ID = @IDDeposito
	IF @ManejaUbicaciones = 1 
		BEGIN
			IF @Modo = 1
				SELECT  TOP 1 @IDUbicacion = U.ID
				FROM CK_ArticulosxUbicacion UA
				INNER JOIN CK_Ubicaciones U ON U.ID = UA.Ubicacion
				WHERE UA.IDArticulo = @IDArticulo AND U.IDDeposito = @IDDeposito AND UA.Cantidad > 0
				ORDER BY U.OrdenRecorrido
			ELSE
				SELECT TOP 1 @IDUbicacion = U.ID
				FROM CK_ArticulosxUbicacion UA
				INNER JOIN CK_Ubicaciones U ON U.ID = UA.Ubicacion
				WHERE UA.IDArticulo = @IDArticulo AND U.IDDeposito = @IDDeposito AND UA.Cantidad > 0
				ORDER BY CONVERT(INT, UA.Cantidad)
		END

	RETURN 	@IDUbicacion
END



(1 rows affected)
