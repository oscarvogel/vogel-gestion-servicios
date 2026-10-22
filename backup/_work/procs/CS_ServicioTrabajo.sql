CREATE    FUNCTION CS_ServicioTrabajo(@IDTrabajo INT, @IDAnt INT)
RETURNS  INT
AS
BEGIN
	declare @A INT
	SELECT Top 1 @A = ID
	FROM Partes  P
	WHERE NroOrden = @IDTrabajo AND Tipo = 2 AND ID > @IDAnt Order by ID
	RETURN @A
END




(1 rows affected)
