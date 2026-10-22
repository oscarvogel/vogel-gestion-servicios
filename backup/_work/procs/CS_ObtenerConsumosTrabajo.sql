
CREATE  Function CS_ObtenerConsumosTrabajo(@IDTrabajo int,@Tipo smallint)
Returns varchar(8000)
AS
Begin
declare @Datos varchar(8000)
set @Datos=''
select @Datos = @Datos + convert(varchar(10),Sum(Cantidad))+'x[' +rtrim(NumeroParte)+'] '+rtrim(Descripcion)+'
'
From Partes Where NroOrden = @IDTrabajo AND Tipo = @Tipo
Group By NumeroParte, Descripcion
return @Datos
end




(1 rows affected)
