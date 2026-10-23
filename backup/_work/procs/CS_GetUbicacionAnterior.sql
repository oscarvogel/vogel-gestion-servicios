CREATE function [dbo].[CS_GetUbicacionAnterior] (@IDTrabajo int)
returns int
as
BEGIN
declare @TU int=0 --por defecto en el cliente
declare @TUA int=null
declare @U int, @UA int
select @U=max(ID) from CS_UbicacionEquipoLog U Where IDTrabajo = @IDTrabajo
Select @TU=TipoUbic from CS_UbicacionEquipoLog where ID = @UA
select @UA=max(ID) from CS_UbicacionEquipoLog U Where ID<@U AND TipoUbic <> @TU AND IDTrabajo = @IDTrabajo 
Select @TUA=TipoUbic from CS_UbicacionEquipoLog where ID = @UA
return @TUA
END


(1 rows affected)
