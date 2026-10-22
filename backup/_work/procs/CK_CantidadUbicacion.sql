
CREATE FUNCTION CK_CantidadUbicacion (@IDUbicacion INT, @IDArticulo INT)
RETURNS  Decimal(19, 6)
AS
BEGIN
	DECLARE @Stock Decimal(19, 6)

	SELECT  @Stock = UA.Cantidad
	FROM CK_ArticulosxUbicacion UA
	WHERE UA.IDArticulo = @IDArticulo AND UA.Ubicacion = @IDUbicacion

	RETURN 	@Stock
END




(1 rows affected)
