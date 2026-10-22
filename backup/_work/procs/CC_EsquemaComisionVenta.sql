
CREATE FUNCTION [dbo].[CC_EsquemaComisionVenta](@Vendedor INT, @IDPolitica INT)
RETURNS INT
AS 
BEGIN
	DECLARE @Esquema INT = NULL 									
	-- Buscar para el Usuario especificamente	
	SELECT @Esquema = ID FROM CC_ComisionxUsuario WHERE IDModulo = 1 AND IDUsuario = @Vendedor AND IDPolitica = @IDPolitica
	-- Buscar para todos los usuarios
	IF @Esquema IS NULL SELECT @Esquema = ID FROM CC_ComisionxUsuario WHERE IDModulo = 1 AND IDUsuario = 0 AND IDPolitica = @IDPolitica
	RETURN @Esquema
END

(1 rows affected)
