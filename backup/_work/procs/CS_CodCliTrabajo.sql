CREATE FUNCTION dbo.CS_CodCliTrabajo(@IDTrabajo INT)
RETURNS INT
AS
BEGIN
	DECLARE @CodCli INT = 0
	DECLARE @Co INT, @Ca INT, @Cd INT					-- Cliente Orden, Cliente Area, Cliente Defecto

	SELECT @Cd = CONVERT(INT, DatoAlfa) FROM CC_ConfigData WHERE Propiedad = 'ClienteDefecto'

	SELECT @Co = T.CodCli, @Ca = P.CodCli
	FROM CS_Trabajos T WITH (NOLOCK)
	INNER JOIN CS_PoliticasxArea P WITH (NOLOCK) ON P.ID = T.IDPolitica
	WHERE T.IDTrabajo = @IDTrabajo

	SET @CodCli = @Cd												-- Inicializar con cliente defecto
	IF @Co > 0 
		SET @CodCli = @Co									-- Si tiene la orden, es el de la orden
	ELSE IF @Ca > 0
		SET @CodCli = @Ca									-- Si no tiene la orden, pero tiene la politica, el de la politica

	RETURN @CodCli
END



(1 rows affected)
