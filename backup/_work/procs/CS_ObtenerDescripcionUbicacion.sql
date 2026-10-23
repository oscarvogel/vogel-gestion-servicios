
CREATE Function [dbo].[CS_ObtenerDescripcionUbicacion](@IDTrabajo int)
returns varchar(500)
as
BEGIN
	declare @TipoUbic int
	declare @DescTipoUbic varchar(500)
	declare @Ubic varchar(500)
	declare @WEB bit=0

	if exists(select * from CC_UsuarioActual where IDProceso = @@SPID and Sistema in ('WA'))
		set @WEB =1

	Select @TipoUbic=T.TipoUbic, @DescTipoUbic=case when @WEB=1 then U.DescripcionWeb else U.Descripcion end, @Ubic=T.Ubicacion
	from CS_Trabajos T
	left join CS_TipoUbicaciones U on U.ID = coalesce(T.TipoUbic,0)
	Where IDTrabajo = @IDTrabajo

	if right(@DescTipoUbic ,1)=':'
		set @DescTipoUbic=@DescTipoUbic+' '+coalesce(@Ubic,'')

	return @DescTipoUbic
END


(1 rows affected)
