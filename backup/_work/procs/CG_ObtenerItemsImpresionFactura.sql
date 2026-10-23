
CREATE Procedure [dbo].[CG_ObtenerItemsImpresionFactura]
@IDRemito int,
@IDDocumento int,
@Items bit,
@XML xml=null out
as
set nocount ON
Declare @SQLCampos nvarchar(4000)
Declare @SQLCamposCA nvarchar(4000)
Declare @SQLCamposDA nvarchar(4000)
Declare @SQL nvarchar(4000)
Declare @SQLGroupBy nvarchar(4000)
Declare @SQLGroupByFinal nvarchar(4000)
Declare @SQLOrderBy nvarchar(4000)
Declare @Campo varchar(50)
Declare @CampoA varchar(50)
declare @CS_NoListaItems int=0
declare @CS_FacturarTrabajoRealizado bit=0
Declare @SQLFinal nvarchar(max)

Select @SQLCampos='',@SQLCamposDA='',@SQLCamposCA='', @SQL='',@SQLGroupBy='', @SQLOrderBy=' Order By ItemNro'
declare @CotFactura varchar(10)
select @CotFactura = convert(varchar(10),Cotizacion) from CG_Facturas where ID = @IDRemito

declare @campos CURSOR

SET @campos = CURSOR LOCAL FAST_FORWARD FOR
	--select Nombre From objetosxdocumento Where nombre like 'CA[\_]%' and Documento=@IDDocumento
	select Nombre From CC_CamposAdicionales_Definicion Where AplicableA=2
open @campos 
FETCH NEXT FROM @campos INTO @Campo
WHILE @@FETCH_STATUS=0 BEGIN
	set @CampoA = replace(@Campo,'CA_','')
	select @SQLCamposCA=@SQLCamposCA+', CA.['+@CampoA+'] as [CA_'+@Campo+']', @SQLGroupBy=@SQLGroupBy+', CA.['+@CampoA+']'
	FETCH NEXT FROM @campos INTO @Campo
END
close @campos

/*
SET @campos = CURSOR LOCAL FAST_FORWARD FOR
	select Nombre From objetosxdocumento Where CampoID=-5 and Documento=@IDDocumento
open @campos 
FETCH NEXT FROM @campos INTO @Campo
WHILE @@FETCH_STATUS=0 BEGIN
	set @CampoA = replace(@Campo,'DA_','')
	select @SQLCamposDA=@SQLCamposDA+', DA.['+@CampoA+'] as ['+@Campo+']', @SQLGroupBy=@SQLGroupBy+', DA.['+@CampoA+']'
	FETCH NEXT FROM @campos INTO @Campo
END
close @campos
*/

SET @campos = CURSOR LOCAL FAST_FORWARD FOR
	select Nombre From CC_CamposAdicionales_Definicion Where AplicableA=11
open @campos 
FETCH NEXT FROM @campos INTO @Campo
WHILE @@FETCH_STATUS=0 BEGIN
	set @CampoA = replace(@Campo,'DA_','')
	select @SQLCamposDA=@SQLCamposDA+', DA.['+@CampoA+'] as [DA_'+@Campo+']', @SQLGroupBy=@SQLGroupBy+', DA.['+@CampoA+']'
	FETCH NEXT FROM @campos INTO @Campo
END
close @campos

select @CS_NoListaItems=CONVERT(int,DatoAlfa) from CC_ConfigData where Propiedad = 'CS_NoListaItems'	
select @CS_FacturarTrabajoRealizado=CONVERT(bit,DatoAlfa) from CC_ConfigData where Propiedad = 'CS_FacturarTrabajoRealizado'	


Set @SQLCampos = 'I.ID, I.Referencia as Codigo, I.Descripcion, Coalesce(convert(varchar,A.DescripcionDetallada), I.Descripcion) as DescripcionDetallada, I.ItemNro, I.Costo, I.Venta, I.ItemStockRelacionado, I.Cotizacion, M.Descripcion as Marca, I.Facturado, I.PorcImpuesto, I.PorcDto, I.ImpExcento, A.CodigoOpcional, 
dbo.CC_ConvertiraMoneda(I.Venta, null, null, I.Cotizacion, '+@CotFactura+') as VentaF,
dbo.CC_ConvertiraMoneda(I.Facturado, null, null, I.Cotizacion, '+@CotFactura+') as FacturadoF,
dbo.CC_ConvertiraMoneda(I.PrecioBase, null, null, I.Cotizacion, '+@CotFactura+') as PrecioBaseF,
dbo.CC_ConvertiraMoneda(I.ImpExcento, null, null, I.Cotizacion, '+@CotFactura+') as ImpExcentoF'

Set @SQLGroupByFinal = 'I.ID, I.Referencia, I.Descripcion, Coalesce(convert(varchar,A.DescripcionDetallada), I.Descripcion), I.ItemNro, I.Costo, I.Venta, I.ItemStockRelacionado, I.Cotizacion, I.Facturado, M.Descripcion, I.PorcImpuesto, I.PorcDto, I.ImpExcento, A.CodigoOpcional,
dbo.CC_ConvertiraMoneda(I.Venta, null, null, I.Cotizacion, '+@CotFactura+') ,
dbo.CC_ConvertiraMoneda(I.Facturado, null, null, I.Cotizacion, '+@CotFactura+'),
dbo.CC_ConvertiraMoneda(I.PrecioBase, null, null, I.Cotizacion, '+@CotFactura+'),
dbo.CC_ConvertiraMoneda(I.ImpExcento, null, null, I.Cotizacion, '+@CotFactura+')' +@SQLGroupBy

if @SQLCamposCA<>'' 
	Set @SQLCampos =@SQLCampos + @SQLCamposCA	--Agergo los campos Adicionales

if @SQLCamposDA<>'' BEGIN
	Set @SQLCampos =@SQLCampos + @SQLCamposDA	--Agergo los DAtos del item
	SET @SQLCampos = @SQLCampos + ', Coalesce(Sum(abs(DA.Cantidad)),sum(I.Cantidad)) as Cantidad' --Tomo la Cantidad del Mov. de Stock
	SET @SQLCampos = @SQLCampos + ', Coalesce(Sum(abs(DA.Cantidad)),sum(I.Cantidad))'
END Else begin
	SET @SQLCampos = @SQLCampos + ', Sum(I.Cantidad) as Cantidad' --Tomo la Cantidad del Item
	SET @SQLCampos = @SQLCampos + ', Sum(I.Cantidad)' --Tomo la Cantidad del Item
end
SET @SQLCampos = @SQLCampos + ' * dbo.CC_ConvertiraMoneda(I.Facturado, null, null, I.Cotizacion, '+@CotFactura+') as TotalItem'

SET @SQLCampos='Select '+@SQLCampos
SET @SQL=' From cg_itemsFacturas I Left Join CC_Articulos A on I.Tipo = 0 AND A.ID = I.ItemID'
SET @SQL=@SQL+' Left Join CC_Marcas M on M.Codigo = A.Marca'
SET @SQL=@SQL+' Left Join cg_itemsFacturas IP on IP.Identificador = I.Identificador AND IP.ItemNro = convert(int,I.ItemNro)'
if @SQLCamposCA<>'' SET @SQL=@SQL+' Left Join CC_caArticulos CA on CA.ID = A.ID'
if @SQLCamposDA<>'' SET @SQL=@SQL+' Left Join CK_DatosArticulo DA on DA.IDItemStock = I.ItemStockRelacionado'
SET @SQL=@SQL+' WHERE I.Identificador = '+convert(varchar,@IDRemito)
if @Items=1 BEGIN
	if coalesce(@CS_NoListaItems,0)=1 
		--SET @SQL=@SQL+' AND (i.Tipo = 2 OR (IP.Tipo <> 2 AND I.Tipo = 0))'
		SET @SQL=@SQL+' AND I.Tipo = 0 AND IP.Tipo not in (2,3)' --Nada de los trabajos
	else
		SET @SQL=@SQL+' AND I.Tipo = 0'
END else
	SET @SQL=@SQL+' AND I.ItemNro = convert(int,I.ItemNro)'
SET @SQL=@SQL+ ' GROUP BY '
set @SQLFinal=@SQLCampos+@SQL+@SQLGroupByFinal
if coalesce(@CS_NoListaItems,0)=1 and @Items=1 BEGIN
	--Aca solo lo de los trabajos...
	set @SQLFinal=@SQLFinal+'
	 UNION ALL 
	 '
	 declare @Descr varchar(1000)='''Según ''+case IP.Tipo When 2 then ''Orden de Servicio'' else ''Liquidación'' end +'' Nº ''+IP.Referencia'
	 if coalesce(@CS_FacturarTrabajoRealizado,0)=1 begin
		set @Descr ='+case IP.Tipo When 2 then (Select left(T.TrabajoRealizado, 255) from CS_Trabajos T Where T.IDtrabajo = IP.ItemID)  else ''Según Liquidación Nº ''+IP.Referencia end '
	 end
	 
	set @SQL = 'Select IP.ID, IP.Referencia as Codigo, ' + @Descr + ' as Descripcion, 
	'+ @Descr +' as DescripcionDetallada, IP.ItemNro, 0 as Costo,
sum(dbo.CC_ConvertiraMoneda(I.Cantidad * I.Venta, null, null, I.Cotizacion, IP.Cotizacion)) as Venta, null as ItemStockRelacionado, IP.Cotizacion, null as Marca,
sum(dbo.CC_ConvertiraMoneda(I.Cantidad * I.Facturado, null, null, I.Cotizacion, IP.Cotizacion)) as Facturado, I.PorcImpuesto, I.PorcDto,
sum(I.ImpExcento) as ImpExcento,
Null as CodigoOpcional,
sum(dbo.CC_ConvertiraMoneda(I.Cantidad * I.Venta, null, null, I.Cotizacion, '+@CotFactura+')) as VentaF,
sum(dbo.CC_ConvertiraMoneda(I.Cantidad * I.Facturado, null, null, I.Cotizacion, '+@CotFactura+')) as FacturadoF,
sum(dbo.CC_ConvertiraMoneda(I.Cantidad * I.PrecioBase, null, null, I.Cotizacion, '+@CotFactura+')) as PrecioBaseF,
sum(dbo.CC_ConvertiraMoneda(I.Cantidad * I.ImpExcento, null, null, I.Cotizacion, '+@CotFactura+')) as ImpExcentoF'
	if @SQLCamposCA	<>'' 
		Set @SQL=@SQL+ @SQLCamposCA	--Agergo los campos Adicionales
	if @SQLCamposDA<>'' 
		Set @SQL=@SQL + @SQLCamposDA	--Agergo los DAtos del item

	SET @SQL=@SQL+ ', 1 as Cantidad' --Tomo la Cantidad del Item
	SET @SQL=@SQL+ ', Sum(dbo.CC_ConvertiraMoneda(I.Cantidad * I.Facturado, null, null, I.Cotizacion, '+@CotFactura+')) as TotalItem'

	SET @SQL=@SQL+' From cg_itemsFacturas I'
	SET @SQL=@SQL+' Left Join cg_itemsFacturas IP on IP.Identificador = I.Identificador AND IP.ItemNro = convert(int,I.ItemNro)'
	if @SQLCamposCA<>'' SET @SQL=@SQL+' Left Join CC_caArticulos CA on CA.ID = 0'
	if @SQLCamposDA<>'' SET @SQL=@SQL+' Left Join CK_DatosArticulo DA on DA.IDItemStock = 0'
	SET @SQL=@SQL+' WHERE I.Identificador = '+convert(varchar,@IDRemito)+' AND IP.Tipo in (2,3) AND I.Tipo = 0'
	SET @SQL=@SQL+' Group by IP.ID, IP.Referencia, IP.ItemNro, IP.Tipo, IP.Cotizacion, I.PorcImpuesto, I.PorcDto '+@SQLGroupBy
	if coalesce(@CS_FacturarTrabajoRealizado,0)=1 set @SQL=@SQL+', IP.ItemID' 
	set @SQLFinal=@SQLFinal+@SQL
END

set nocount OFF

if @XML is null begin
	set @SQLFinal=@SQLFinal+@SQLOrderBy
	exec (@SQLFinal)
end else begin
	set @SQLFinal= 'select @RESULT = (Select * from ('+ @SQLFinal +') Row ' + @SQLOrderBy + ' FOR XML AUTO, TYPE)'
	execute sp_executesql @SQLFinal, N'@RESULT xml output', @RESULT = @XML output
end
set nocount on



(1 rows affected)
