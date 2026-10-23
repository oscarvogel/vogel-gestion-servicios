CREATE Function [dbo].[CS_ObtenerTipoUbicacion](@Lugar int, @FechaRecepcion datetime, @FechaEntrega datetime, @IDTipoCanje INT, @EstadoCanje INT)
returns int
as
BEGIN
	--1 = Usado Recibido
	--2 = Usado Enviado
	--4 = Nuevo Recibido
	--8 = Nuevo Enviado
	--16 = Acreditado

	-- Esto se llama solo cuando no se pudo obtener una ubicacion... (se asume que el registro del trabajo se está generando)
	DECLARE @DestinoCanje INT = 0
	SELECT @DestinoCanje = Destino FROM CS_TiposCanje WHERE ID = @IDTipoCanje

	declare @R int
	if @FechaRecepcion is null OR not @FechaEntrega is null
		--Si No tiene Recepción p ya fue entregada.. esta en el domicilio del cliente!!!
		set @R=0 
	else begin
		IF @FechaRecepcion IS NULL BEGIN
			IF dbo.GetSistemaActual() = 'CS' 
				set @R=1	--en casa central
			ELSE	
				set @R=2	--en taller del responsable
		END ELSE BEGIN
			IF COALESCE(@IDTipoCanje, 0) = 0 OR @EstadoCanje & 8 = 8		
				SET @R=1								-- NO ES CANJE o NO SE ENVIO, esta en taller propio
			ELSE IF @EstadoCanje & 8 = 8 BEGIN 			-- El nuevo ya esta enviado --> Ubicacion = destino del canje
				IF @DestinoCanje = 1 SET @R = 0			-- DESTINO 1: En el Usuario
				ELSE IF @DestinoCanje = 2 SET @R = 3	-- DESTINO 2: Comercio
				ELSE IF @DestinoCanje = 3 SET @R = 2	-- DESTINO 3: en el Agente
			END 
		END
	end
	return @R
end




(1 rows affected)
