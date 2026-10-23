CREATE Function [dbo].[CS_GetEstadoTrabajo](@Trabajo INT)
returns varchar(40)
AS
Begin
	DECLARE @R varchar(100)
	DECLARE @TipoUbic INT
	DECLARE @TipoAnulacion INT
	DECLARE @MotivoAnulacion VARCHAR(100)
	DECLARE @FacturaEmitida Varchar(25)
	DECLARE @Estado INT
	DECLARE @Orden VARCHAR(10)
	declare @FechaVisita varchar(20)
	DECLARE @OrdenDeRetiro int 
	DECLARE @AsistirEn INT

	SELECT @TipoUbic = T.TipoUbic, @TipoAnulacion = T.TipoAnulacion, @MotivoAnulacion = Ma.Motivo, @FacturaEmitida = T.FacturaEmitida, @AsistirEn = T.AsistirEn,
	@Estado = COALESCE(T.Estado, -1), @FechaVisita=convert(varchar,T.FechaVisita,103), @OrdenDeRetiro = T.OrdenDeRetiro
	FROM CS_Trabajos T
	LEFT JOIN CS_MotivosAnulacion Ma ON Ma.ID = T.TipoAnulacion
	WHERE T.IDTrabajo = @Trabajo
	SET @R = CASE  
				WHEN coalesce(@OrdenDeRetiro,-1)<>-1 THEN 'Para Retirar'
				WHEN @Estado = -1 AND @AsistirEn = 0 AND @TipoUbic NOT IN (1,2)  THEN 'Esperando Recepción'				-- Asistir en Taller, y no esta en taller
				WHEN @Estado = -1 AND @AsistirEn = 0 AND @TipoUbic IN (1,2)  THEN 'Para Iniciar'					-- Asistir en Taller y esta en taller
				WHEN @Estado = -1 AND @AsistirEn = 1 AND @TipoUbic NOT IN (1,2) THEN 'Para Visitar' + coalesce(' el '+@FechaVisita,'')		-- ASistir en Domicilio y no esta en taller
				WHEN @Estado = -1 THEN 'Para Iniciar'
				WHEN @Estado = 0 THEN 'Para Presupuestar'
				WHEN @Estado = 1 THEN 'Para Informar'
				WHEN @Estado = 2 THEN 'En Aprobación'
				WHEN @Estado = 3 THEN 'Faltan Requisitos'
				WHEN @Estado = 4 THEN 'Abierta'
				WHEN @Estado = 5 THEN 'Rechazada'
				WHEN @Estado = 6 AND COALESCE(@TipoAnulacion, -1) = -1 THEN 'Anulada sin iniciar'
				WHEN @Estado = 6 AND COALESCE(@TipoAnulacion, -1) >= 0 THEN @MotivoAnulacion
				WHEN @Estado = 7 THEN 'Cerrada'
				WHEN @Estado = 8 AND @FacturaEmitida = '' THEN 'Liquidada'
				WHEN @Estado = 8 AND @FacturaEmitida <> '' THEN 'Facturada'
			ELSE
				'Error'
			END
	return @R
End


(1 rows affected)
