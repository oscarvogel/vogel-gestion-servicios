CREATE FUNCTION [dbo].[CS_ControlStockTecnico](@IDTrabajo INT, @IDPolitica INT, @IDUsuario INT)
RETURNS BIT
AS
BEGIN
	DECLARE @R BIT = 0
	IF @IDUsuario > 0 BEGIN
		-- Si hay un usuario
		IF dbo.CC_PermisoUsuario(@IDUsuario, 'CS_EvitarControlStock', Null) = 0 BEGIN
			-- Si el usuario no evita control, depende de la cuenta de stock de la politica
			IF COALESCE(@IDTrabajo, 0) > 0 
				SELECT @R = COALESCE(Cs.StockTecnico, 1)
				FROM CK_ConsumosCiberService Cs WITH (NOLOCK)
				INNER JOIN CS_Trabajos T WITH (NOLOCK) ON T.IDPolitica = Cs.IDPolitica 
				WHERE T.IDTrabajo = @IDTrabajo
			ELSE
				SELECT @R = COALESCE(Cs.StockTecnico, 1)
				FROM CK_ConsumosCiberService Cs WITH (NOLOCK)
				WHERE Cs.IDPolitica = @IDPolitica
		END
	END
	RETURN @R
END


(1 rows affected)
