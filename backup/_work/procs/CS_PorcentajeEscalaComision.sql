CREATE FUNCTION [dbo].[CS_PorcentajeEscalaComision](@IDTrabajo INT, @Esquema INT)
RETURNS Decimal(19, 6)
AS 
BEGIN
	DECLARE @Ptj Decimal(19,6)
	Declare @DemoraDespacho INT
	DECLARE @DemoraCierre INT
	DECLARE @DemoraService INT
	
	SELECT @DemoraCierre = DATEDIFF(d, FechaAlta, FechaCerrada) FROM CS_Trabajos WHERE IDTrabajo = @IDTrabajo	
	SET @DemoraDespacho = dbo.CS_DemoraDespacho(@IDTrabajo)
	SET @DemoraService = @DemoraCierre - @DemoraDespacho 
	
	SELECT TOP 1 @Ptj = Porcentaje FROM CS_EscalasDescuentosEsquema WHERE Esquema = @Esquema AND @DemoraService < Dias Order by Dias
	SELECT @Ptj = COALESCE(@Ptj, PorcentajeMaximo) FROM CC_EsquemasComision WHERE ID = @Esquema
	RETURN COALESCE(@Ptj, 0)
END


(1 rows affected)
