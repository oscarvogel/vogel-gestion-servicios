CREATE FUNCTION [dbo].[CC_ObtenerComisionaFecha](@IDArticulo INT, @Esquema INT, @Fecha DATETIME)
RETURNS DECIMAL(19, 5)
AS
BEGIN
	DECLARE @ComisionH DECIMAL(19, 5) = 0

	SELECT TOP 1 @ComisionH = Valor
	FROM CC_Comisiones_Historico WHERE IDArticulo = @IDArticulo AND Esquema = @Esquema AND Fecha <= @Fecha
	ORDER BY Fecha DESC
	RETURN @ComisionH
END

(1 rows affected)
