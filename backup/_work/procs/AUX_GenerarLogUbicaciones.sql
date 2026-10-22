
CREATE PROCEDURE [dbo].[AUX_GenerarLogUbicaciones]
as
set nocount on
declare @t table(ID int identity(1,1), IDTrabajo int, FechaDesde datetime, FechaHasta datetime, TipoUbic tinyint, Ubicacion varchar(200))
declare @IDTrabajo int, @Ubic varchar(200), @Fecha datetime, @FechaAlta datetime, @UbicActual varchar(200)
declare @UbicAnt varchar(200), @IDtrabajoAnt int, @FechaAnt datetime, @ID int, @IDS int, @UbicActANT varchar(200)
declare C cursor local static for
	select T.IDTrabajo, 
		case 
			when T.FechaRecepcion IS null then 'Domicilio del Cliente' --> si no tiene recepcion, nunca pudo cambiar la ubicaciòn
			when T.FechaRecepcion > S.Fecha then 'Domicilio del Cliente'
			else AT.Ubicacion 
		end,
		S.Fecha, T.FechaAlta, 
		case 
			when T.FechaRecepcion IS null then 'Domicilio del Cliente' --> si no tiene recepcion, nunca pudo cambiar la ubicaciòn
			else T.Ubicacion
		end, S.ID
	from CS_Trabajos T
	left join CS_SucesosTrabajo S on  S.IDTrabajo = T.IDTrabajo and S.Suceso = 2  --S.ID = at.IDSuceso 
	left join CS_AuditoriaTrabajos AT on AT.IDTrabajo = T.IDTrabajo and S.ID = at.IDSuceso  
--	where t.IDTrabajo between 128029 and 128029
	order by T.IDTrabajo desc, S.ID 
open C
declare @no bit
fetch next from c into @IDTrabajo, @Ubic, @Fecha, @FechaAlta, @UbicActual, @IDS
while @@FETCH_STATUS=0 BEGIn
	set @no=0
	if @IDTrabajo<>coalescE(@IDtrabajoAnt,0) begin
		--cambio el trabajo, inicializar...
		if coalesce(@UbicActANT,'')<>coalesce(@UbicAnt,'') and coalesce(@ID,0)>0 begin
			--La ultima ubicacion cambiò
			update @t set FechaHasta = @FechaAnt where ID = @ID
			insert into @t(IDTrabajo, FechaDesde, Ubicacion) values (@IDtrabajoAnt,@FechaAnt,@UbicActANT)
		end
		select @UbicAnt=@Ubic, @FechaAnt=@Fecha, @IDtrabajoAnt=@IDTrabajo
		if @IDS>0 begin
			insert into @t(IDTrabajo, FechaDesde, Ubicacion) values (@IDTrabajo,@FechaAlta, @Ubic)
			set @ID=scope_identity()
		end else begin
			insert into @t(IDTrabajo, FechaDesde, Ubicacion) values (@IDTrabajo,@FechaAlta,@UbicActual) --no hubo modificaciones.....
			set @ID=scope_identity()
			select @UbicAnt=@UbicActual, @FechaAnt=@Fecha, @IDtrabajoAnt=@IDTrabajo, @UbicActANT= @UbicActual
			set @no=1
		end
	end 
	if @no=0 begin
		if coalesce(@UbicAnt,'')<>coalesce(@Ubic,'') begin
			--cambio la ubicacion
			update @t set FechaHasta = @FechaAnt where ID = @ID
			insert into @t(IDTrabajo, FechaDesde, Ubicacion) values (@IDTrabajo,@FechaAnt,@Ubic )
			set @ID=scope_identity()
		end
		select @UbicAnt=@Ubic, @FechaAnt=@Fecha, @IDtrabajoAnt=@IDTrabajo, @UbicActANT= @UbicActual
	end
	fetch next from c into @IDTrabajo, @Ubic, @Fecha, @FechaAlta, @UbicActual, @IDS
END
close C
deallocate C
if coalesce(@UbicActANT,'')<>coalesce(@UbicAnt,'') and coalesce(@ID,0)>0 begin
	--La ultima ubicacion cambiò
	update @t set FechaHasta = @FechaAnt where ID = @ID
	insert into @t(IDTrabajo, FechaDesde, Ubicacion) values (@IDtrabajoAnt,@FechaAnt,@UbicActANT)
end
truncate table CS_UbicacionEquipoLog
INSERT INTO [CS_UbicacionEquipoLog]([IDTrabajo],[FechaDesde],[FechaHasta],[TipoUbic],[Ubicacion])
select [IDTrabajo],[FechaDesde],[FechaHasta],
case when Ubicacion like 'Domicilio del Cliente%' then 0
		when Ubicacion like 'Retirada%' then 0
		else 1
END,[Ubicacion] from @t
--ahora actualizar
update CS_Trabajos set FlagSuceso=1, IDUbic = U.ID
from (Select MAX(ID) as ID, IDtrabajo from CS_UbicacionEquipoLog group by IDTrabajo) U where CS_Trabajos.IDTrabajo = U.IDTrabajo



(1 rows affected)
