CREATE FUNCTION [dbo].[CS_SaldoTrabajo](@IDTrabajo INT)
RETURNS DECIMAL(18,2)
AS
BEGIN
	DECLARE @Saldo DECIMAL(18,2)
	DECLARE @Pagos DECIMAL(18,2)
	DECLARE @TotalVendido DECIMAL(18,2)
	DECLARE @Importe DECIMAL(18,2)

	-- El importe de la orden es lo presupuestado o lo consumido, lo que sea mayor
	SELECT @Pagos = SUM(Importe) FROM MovimientosCaja Where TipoDocumentoGenera = 23 AND GeneraEnDocumento = @IDTrabajo AND COALESCE(Pendiente, 0) = 0
	SELECT @TotalVendido = COALESCE(VentaTotal, 0), @Importe = TotalPresupuesto FROM CS_Trabajos WHERE IDTrabajo = @IDTrabajo
	IF COALESCE(@TotalVendido, 0) > COALESCE(@Importe, 0) SET @Importe = COALESCE(@TotalVendido, 0)

	SET @Saldo = COALESCE(@Importe, 0) - COALESCE(@Pagos, 0)
	RETURN @Saldo
END

(1 rows affected)
