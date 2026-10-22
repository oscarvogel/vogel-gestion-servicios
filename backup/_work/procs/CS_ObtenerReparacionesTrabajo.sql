CREATE Function [dbo].[CS_ObtenerReparacionesTrabajo](@IDTrabajo int)
Returns varchar(8000)
AS
Begin
declare @Datos varchar(8000)
set @Datos=''
select @Datos = @Datos + '[' + Sintoma +':' +rtrim(Repuesto)+':'  + Reparacion+ ' ] '+'
'
From PartesIRIS Where NroOrden = @IDTrabajo 
return @Datos
end


(1 rows affected)
