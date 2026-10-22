CREATE Procedure [dbo].[CG_Generar_Factura]
@PoliticaImpresion int,
@Fecha smalldatetime =null,
@CodCli int =null,
@Cliente varchar(60) =null,
@Domicilio varchar(120) =null,
@Localidad varchar(50) =null,
@Provincia varchar(50) =null,
@CodigoPostal varchar(20) =null,
@CategoriaImpuesto int =null,
@CUIT varchar(15) =null,
@CondicionPago smallint =null,
@Vencimiento smalldatetime =null,
@Estimado smalldatetime =null,
@Cotizacion int=null, 
@CentroDeCosto int=null, 
@Vendedor int =null,
@Contacto varchar(60) =null,
@IDContacto int =null,
@Sucursal varchar(50) =null,
@Comentarios varchar(max) =null,
@CuentaContable int =null,
@CuentaContableComprobante int =null,
@IDSucursalCliente int =null,
@Items xml,
@ID int OUT,
@MovimientoStock int out, 
@DepositoSalida int=null,
@CuentaStock int=null
AS

--'@TipoDoc','@Grupo','@SP_AfterUpdate','@SP_AfterCommit','@SP_AfterRollback','@Fecha','@ProximoNumero','@CAI','@VtoCAI'
--'@Hidden_TipoDoc','@Hidden_Grupo','@Hidden_SP_AfterUpdate','@Hidden_SP_AfterCommit','@Hidden_SP_AfterRollback','@Fecha','@Hidden_ProximoNumero','@Hidden_CAI','@Hidden_VtoCAI'


declare @Numero varchar(20)=null
declare @EnSucursal int 
declare @IDProvincia int
declare @AnuladoEl datetime , @AnuladoPor int, @Anulado bit =0
declare @AnuladoImputacionContable int ,@AnuladoImputacionContablePagos int 
declare @MovimientoStockAnulacion int 
declare @Hidden_CAI varchar(15) ,@Hidden_VtoCAI smalldatetime , @CodigoBarras varchar(50) 

declare @CopiasImpresas tinyint , @ImputacionContablePagos int 
declare @Bruto decimal(19, 6) ,@Neto decimal(19, 6) ,@Total decimal(19, 6) , @ImporteExento decimal(19, 6) 

declare @Estado tinyint =0
declare @RealizadoPor int =dbo.GetUsuarioActual()

declare @Discrimina bit
declare @PoliticaImpositiva int 
declare @RealizadoEl smalldatetime =getdate()
declare @ImputacionContable int 
declare @IDSesionCaja int 
declare @IDGrupo int

declare @SQL nvarchar(max)
declare @SQLParams nvarchar(max)
declare @Datos varchar(max)

--Obtener Cliente
if coalesce(@CodCli,0)=0 begin
	--obtener cliente por defecto!
	select @CodCli=convert(int,datoalfa) from CC_ConfigData where Propiedad = 'ClienteDefecto'
end
if coalesce(@CodCli,0)=0 begin
	raiserror('Imposible Facturar sin un cliente válido',16,1)
	return
end
--Obtener Categorìa IVA...
if coalesce(@CategoriaImpuesto,0)=0 begin
	select @CategoriaImpuesto=Categoria from CC_CategoriasxCliente Where Cliente = @CodCli and Impuesto = 1
	if coalesce(@CategoriaImpuesto,0)=0 select @CategoriaImpuesto=convert(int,datoalfa) from CC_ConfigData where Propiedad = 'IVA_CategoriaDefecto'
end
--Obtener El Cuit/Documento
if coalesce(@CUIT,'')='' 
	select @CUIT=Inscripcion from CC_CategoriasxCliente Where Cliente = @CodCli and Impuesto = 1

declare @TipoPrn int, @Formulario int, @Talonario int, @DocImpresion int, @CtaStock int
Select @IDGrupo=GrupoEmite from IVA_Categorias  Where ID = @CategoriaImpuesto
Select @TipoPrn=TipoPrn, @Formulario=Formulario, @Talonario=Talonario, @DocImpresion=Documento, @Datos=Datos, @CtaStock=CtaStock from CG_ConfiguracionxPolitica where IDPolitica = @PoliticaImpresion and TipoDocumento=1 AND Grupo=@IDGrupo

if coalesce(@CtaStock,0)=0 select @CtaStock=convert(int,datoalfa) from CC_ConfigData where Propiedad = 'CuentaStockFacturas'            

            
declare @OK bit=1
--verificar si es posible generar la factura
if @TipoPrn = 1 begin
	set @OK =0
	raiserror('Imposible Facturar con una impresora fiscal',16,1)
	return
end	if @TipoPrn = 0 begin
	if exists(select * from CG_Formularios_Tabla where ID = @Formulario AND Numeracion =0) begin
		set @OK =0
		raiserror('No es posible facturar con formularios Pre Numerados',16,1)
		return
	end
end 
if @OK=0 return

if coalesce(@Cliente,'')='' begin
	--Si no viene un cliente, tomar los datos del codigo de cliente...
	Select @Cliente=C.Cliente, @Domicilio=coalesce(C.Calle+' ','')+coalesce(convert(varchar,C.Altura)+' ','')+coalesce(C.Otros,''), @Localidad = C.Localidad, @IDProvincia=C.Provincia, @CodigoPostal=C.CodigoPostal 
	FROM CC_Clientes C Where C.CodCli = @CodCli 
	Select @Provincia=Provincia from CC_Provincias where ID = @IDProvincia 
end else --Se asume que si viene cliente, vienen todos los datos relacionados (domicilio, localidad, provincia, CP)
	Select @IDProvincia=ID from CC_Provincias where Provincia  = @Provincia 

select @Discrimina = Discriminar from IVA_Categorias where ID = @CategoriaImpuesto 


if coalesce(@CondicionPago ,0)=0 begin
	raiserror ('Condición de Pago inválida',16,1)
	return
end

if @Vencimiento is null begin
	--Obtener el vencimiento...
	select @Vencimiento=DATEADD(d, DiasVto1,@Vencimiento) from CG_Condiciones where Codigo = @CondicionPago 
	set @Vencimiento=coalesce(@Vencimiento,convert(date,getdate()))
end

Declare @IF TABLE ([Tipo] [tinyint] NULL, [SubTipo] [smallint] NOT NULL, [ItemNro] [decimal](19, 4) NULL, [ItemID] [int] NULL,
					[Descripcion] [varchar](255) NULL,[Cantidad] [decimal](19, 6) NOT NULL,[Costo] [decimal](19, 6) NULL,
					[Venta] [decimal](19, 6) NOT NULL,[Facturado] [decimal](19, 6) NULL,[PorcImpuesto] [decimal](19, 6) NULL,
					[PorcBase] [decimal](19, 6) NULL,[Cotizacion] [int] NULL,[Referencia] [varchar](50) NULL,[ItemMovStk] [int] NULL,
					[TipoOrig] [smallint] NULL,[ItemIDOrig] [int] NULL,[PoliticaImpositiva] [int] NULL,[ImpExcento] [decimal](19, 6) NULL,
					[Vendedor] [int] NULL,[NetoGravado] [decimal](19, 6) NULL,[CotizacionCosto] [int] NULL,[PrecioBase] [decimal](19, 6) NULL,
					[PorcDto] [decimal](9, 4) NULL,[ItemStockRelacionado] [int] NULL, PrecioCon decimal(19,6), tmpID int identity(1,1))

insert into @IF (Tipo, SubTipo, ItemNro, ItemID, Descripcion, Cantidad, Costo, Venta, Facturado, PorcImpuesto, PorcBase, Cotizacion, Referencia, 
			     ItemMovStk, TipoOrig, ItemIDOrig, PoliticaImpositiva, ImpExcento, Vendedor, NetoGravado, CotizacionCosto, PrecioBase, PorcDto, ItemStockRelacionado)
select coalesce(n.value('@Tipo','tinyint'),0),
	   n.value('@SubTipo','smallint'), 
	   n.value('@ItemNro','decimal(19, 4)'), 
	   n.value('@ItemID','int'), 
	   n.value('@Descripcion','varchar(255)'), 
	   coalesce(n.value('@Cantidad','decimal(19, 6)'),0) ,
	   coalesce(n.value('@Costo','decimal(19, 6)'),0) ,
	   coalesce(n.value('@Venta','decimal(19, 6)'),0), --Precio Sin
	   n.value('@Facturado','decimal(19, 6)'), --< calcular
	   n.value('@PorcImpuesto','decimal(19, 6)'), 
	   n.value('@PorcBase','decimal(19, 6)'), 
	   n.value('@Cotizacion','int'), 
	   n.value('@Referencia','varchar(50)'), 
	   n.value('@ItemMovStk','int'), 
	   n.value('@TipoOrig','smallint'), 
	   n.value('@ItemIDOrig','int'), 
	   n.value('@PoliticaImpositiva','int'), 
	   n.value('@ImpExcento','decimal(19, 6)'), 
	   n.value('@Vendedor','int'), 
	   n.value('@NetoGravado','decimal(19, 6)'), --< calcular 
	   n.value('@CotizacionCosto','int'), 
	   n.value('@PrecioBase','decimal(19, 6)'), 
	   n.value('@PorcDto','decimal(9, 4)'), 
	   n.value('@ItemStockRelacionado','int')
from @Items.nodes('//*:Item') t(n)

declare @CategoriaObjeto int
Select @CategoriaObjeto = convert(int,convert(varchar,DatoAlfa)) From CC_ConfigData Where Propiedad = 'IVA_TasaDefecto'
set @CategoriaObjeto = coalesce(@CategoriaObjeto,1)
--Especifico la tasa predeterminada si no tiene....
update @IF set PoliticaImpositiva = @CategoriaObjeto where coalesce(PoliticaImpositiva,0)=0

--completar valores faltantes...
update I set PrecioBase = coalesce(I.PrecioBase,Venta), PorcBase=coalesce(I.PorcBase,100),
NetoGravado = I.Cantidad * dbo.CC_ConvertiraMonedaSinRedondeo(I.Venta ,null,null,I.Cotizacion,@Cotizacion), 
PrecioCon = dbo.CC_ConvertiraMoneda(dbo.IVA_AplicarImpuesto(I.Venta,@CategoriaImpuesto,I.PoliticaImpositiva),null,null,I.cotizacion,I.Cotizacion)  , 
Facturado = Venta --asumo que discrimina
from  @IF I
if @Discrimina = 0 --si no discrimina, el facturado lleva IVA
	update @IF set Facturado = PrecioCon

select @Bruto = SUM(dbo.CC_ConvertiraMoneda(I.Facturado,null,null,I.Cotizacion,@Cotizacion) *I.Cantidad),
	   @Neto = SUM(dbo.CC_ConvertiraMoneda(I.Facturado,null,null,I.Cotizacion,@Cotizacion)*I.Cantidad),
	   @ImporteExento =SUM(I.ImpExcento*I.Cantidad),
	   @Total = SUM(dbo.CC_ConvertiraMoneda(I.PrecioCon,null,null,I.Cotizacion,@Cotizacion)*I.Cantidad) from @IF I where Tipo=0

declare @Tasas as TablaPercepciones
select * into #TablaPercepciones from @Tasas
--Obtener los registros de IVA
insert into @Tasas
select T.ID, 1, SUM(I.NetoGravado), SUM(I.NetoGravado), T.Porcentaje, 0, T.Descripcion, 'IVA',SUM(I.NetoGravado)*T.Porcentaje/100,null,@Discrimina
from  @IF I
inner join IVA_Tasas T on T.ID = I.PoliticaImpositiva
Where I.Tipo=0
group by T.ID, T.Porcentaje, T.Descripcion

--Calcular percepciones...
declare @tasasXML xml=(
	select  I.IDImpuesto as '@ID',
		(Select * from @Tasas T Where T.IDImpuesto = I.IDImpuesto for XML Path('Tasa'), TYPE)
	From (select distinct IDImpuesto from @Tasas )I
	for xml path('Impuesto'),root('Datos'), TYPE)

declare @ImpPer decimal(19,6)
exec CG_CalcularPercepciones @tasasXML, @ImpPer out

insert into @Tasas
select * from #TablaPercepciones 
drop table #TablaPercepciones 
--Sumamos las percepciones al total...
set @Total =@Total +coalesce(@ImpPer,0)
--
declare @Hidden_SP_AfterUpdate nvarchar(100),@Hidden_SP_AfterCommit nvarchar(100),@Hidden_SP_AfterRollback nvarchar(100)
if coalesce(@Total,0) >0 begin
	begin try
		begin tran
		--Ver si hacen falta movimientos de Stock...
		if coalesce(@DepositoSalida,0)<>0 and exists(Select * from @IF where convert(int,ItemNro)=ItemNro and Tipo=0 and ItemStockRelacionado is null) begin
			--hay que generar la salida de stock
			set @MovimientoStock=0
			set @CuentaStock = coalesce(@CuentaStock ,@CtaStock)
            			
			--cabecera movimiento
			INSERT INTO CK_MovimientosStock (Fecha,Genera,Tipo,Comentarios,EntregaRecibe,CuentaStock,Deposito,Cotizacion,Sucursal,TipoMovimiento, Titular)
			Select getdate(), @RealizadoPor, 1, 'Movimiento de Salida por Nuestra Factura Nº ',  0, @CuentaStock, @DepositoSalida, 1, null, 5, @CodCli
			set @MovimientoStock = scope_identity()
			--items
			Insert into CK_ItemsMovStock (Origen, Identificador, ItemNro, Tipo, SubTipo, ItemID, Descripcion, Cantidad, Cotizacion, pOrden)
			Select 0, @MovimientoStock, ROW_NUMBER() OVER(ORDER BY tmpID) AS ItemNro, SubTipo-1, 0, ItemID, Descripcion, -Cantidad, 1, -tmpID
			from @IF where convert(int,ItemNro)=ItemNro and Tipo=0 and ItemStockRelacionado is null
			--actualiza en items el id del mov
			update I set ItemMovStk= IM.ID, ItemStockRelacionado = IM.ID
			from @IF I 
			inner join CK_ItemsMovStock IM on IM.Identificador = @MovimientoStock and IM.pOrden = -I.tmpID
			update CK_ItemsMovStock set pOrden = 0 where Identificador = @MovimientoStock 
		end
		--Obtener numero...
		declare @Quedan int 
		if @TipoPrn=0 begin
			exec [CG_ObtenerProximoNumero] 1,@PoliticaImpresion,@IDGrupo,@Numero OUT,@Hidden_CAI  OUT,@Hidden_VtoCAI OUT,@Quedan OUT
			set @CodigoBarras=dbo.CG_ObtenerCodigoBarras(1,@Numero, @Hidden_CAI, @Hidden_VtoCAI)
		end else begin
			declare @SP_ProximoNumero varchar(100)
			select @SP_ProximoNumero=SP	 from CC_Consultas Where IDTabla = @TipoPrn
			select @SQL = @SP_ProximoNumero+N' @Hidden_TipoDoc=1, @Hidden_Grupo=@Hidden_Grupo, @Hidden_SP_AfterUpdate=@Hidden_SP_AfterUpdate OUT, @Hidden_SP_AfterCommit=@Hidden_SP_AfterCommit OUT, @Hidden_SP_AfterRollback=@Hidden_SP_AfterRollback OUT, @Hidden_Fecha=@Fecha, '
			if coalesce(@Datos,'')<>'' begin
				declare @D xml	= convert(xml,@Datos)
				select @SQL=@SQL+'@'+t.c.value('local-name(.)','nvarchar(50)')+'='+quotename(t.c.value('(.)','nvarchar(50)'),'''')+', ' from @D.nodes('//Parametros/*') t(c)	
			end 
			select @SQL = @SQL + N'@Hidden_ProximoNumero = @Hidden_ProximoNumero OUT, @Hidden_CAI = @Hidden_CAI OUT, @Hidden_VtoCAI = @Hidden_VtoCAI OUT'
			select @SQLParams = N'@Hidden_Grupo int, @Hidden_SP_AfterUpdate varchar(100) OUT, @Hidden_SP_AfterCommit varchar(100) OUT, @Hidden_SP_AfterRollback varchar(100) OUT, @Hidden_Fecha datetime, @Hidden_ProximoNumero varchar(14) OUT, @Hidden_CAI varchar(20) OUT, @Hidden_VtoCAI datetime OUT'
			exec sp_executesql @SQL, @SQLParams,@Hidden_Grupo=@IDGrupo, @Hidden_SP_AfterUpdate=@Hidden_SP_AfterUpdate OUT, @Hidden_SP_AfterCommit=@Hidden_SP_AfterCommit OUT, @Hidden_SP_AfterRollback=@Hidden_SP_AfterRollback OUT, @Hidden_Fecha=@Fecha,@Hidden_ProximoNumero = @Numero OUT, @Hidden_CAI = @Hidden_CAI OUT, @Hidden_VtoCAI = @Hidden_VtoCAI OUT
		end
		
		--crear el registro de factura
		INSERT INTO [CG_Facturas_Tabla]
           ([Numero],[Fecha],[CodCli],[Cliente],[Domicilio],[Localidad],[Provincia],[CodigoPostal],[CategoriaImpuesto],[CUIT],[CondicionPago]
			,[Vencimiento],[Estimado],[Bruto],[Neto],[Total],[Estado],[MovimientoStock],[Cotizacion],[RealizadoPor],[CentroDeCosto],[Anulado]
			,[MovimientoStockAnulacion],[PoliticaImpositiva],[RealizadoEl],[Vendedor],[ImporteExento],[PoliticaImpresion],[CAI],[VtoCAI],[CodigoBarras]
			,[Contacto],[IDContacto],[Sucursal],[CopiasImpresas],[Comentarios],[ImputacionContable],[IDSesionCaja],[CuentaContable],[ImputacionContablePagos]
			,[AnuladoEl],[AnuladoPor],[AnuladoImputacionContable],[AnuladoImputacionContablePagos],[CuentaContableComprobante],[EnSucursal],[IDSucursalDestino])
		VALUES
           (@Numero,@Fecha,@CodCli,@Cliente,@Domicilio,@Localidad,@Provincia,@CodigoPostal,@CategoriaImpuesto,@CUIT,@CondicionPago
			,@Vencimiento,@Estimado,@Bruto,@Neto,@Total,@Estado,@MovimientoStock,@Cotizacion,@RealizadoPor,@CentroDeCosto,@Anulado
			,@MovimientoStockAnulacion,@PoliticaImpositiva,@RealizadoEl,@Vendedor,@ImporteExento,@PoliticaImpresion,@Hidden_CAI,@Hidden_VtoCAI,@CodigoBarras
			,@Contacto,@IDContacto,@Sucursal,@CopiasImpresas,@Comentarios,@ImputacionContable,@IDSesionCaja,@CuentaContable,@ImputacionContablePagos
			,@AnuladoEl,@AnuladoPor,@AnuladoImputacionContable,@AnuladoImputacionContablePagos,@CuentaContableComprobante,@EnSucursal,@IDSucursalCliente)
		select @ID=SCOPE_IDENTITY()
		--crear los itemes
		INSERT INTO [CG_ItemsFacturas]
			([Identificador],[Tipo],[SubTipo],[ItemNro],[ItemID],[Descripcion],[Cantidad],[Costo],[Venta],[Facturado],[PorcImpuesto],[PorcBase],[Cotizacion],[Referencia],
			[ItemMovStk],[TipoOrig],[ItemIDOrig],[PoliticaImpositiva],[ImpExcento],[Vendedor],[NetoGravado],[CotizacionCosto],[PrecioBase],[PorcDto],[ItemStockRelacionado])
		Select @ID, [Tipo],[SubTipo],[ItemNro],[ItemID],[Descripcion],[Cantidad],[Costo],[Venta],[Facturado],[PorcImpuesto],[PorcBase],[Cotizacion],[Referencia],
			[ItemMovStk],[TipoOrig],[ItemIDOrig],[PoliticaImpositiva],[ImpExcento],[Vendedor],[NetoGravado],[CotizacionCosto],[PrecioBase],[PorcDto],[ItemStockRelacionado]		
		from @IF 
		--crear dtorgos
		Insert Into CG_DtoRgoFacturas (Acumulativo, Identificador, Impuesto, ItemNro, DtoRgoID, Descripcion, Porcentaje, Importe, BaseImpuesto, Tipo, Tag) 
		Select 0, @ID, T.IDImpuesto, ROW_NUMBER() OVER(order by IDImpuesto, Tipo, ID) ,T.ID,T.Abreviatura , T.Porcentaje,T.ValorImpuesto, T.BaseConDtos, T.Tipo , T.Tag   
		from @Tasas T
   				
   		--Generar Movimiento en CtaCte...
   		insert into CC_MovimientosCtaCte(Fecha, Tipo, Titular, IDAfecta, Afecta, Importe , Comentarios,ReferenciaAfecta,
   		IDOrigen,Origen,Anulado,ReferenciaOrigen,Cotizacion,Asignado,RealizadoPor)
   		Select F.Fecha, T.ID , F.CodCli, F.ID, 1, F.Total * T.Signo , replace(replace(T.Descripcion,'%N%',F.Numero ),'%C%', F.Cliente),F.Numero,
   		F.ID,1,0,F.Numero,F.Cotizacion,0,F.RealizadoPor 
   		FROM CG_Facturas_Tabla F 
   		Inner Join CC_TiposMovimientosCtaCte T on T.TipoDocumento = 1
   		Where F.ID = @ID

		--Meter Pagos de Trabajos si es que existen
		insert into CG_ValoresRecibo(IDRecibo,ItemNro, Tipo, IDValor, Importe, Cotizacion, ImporteMoneda, CajaEntrada, Cuotas, Entidad, Concepto)
		select  -@ID, ROW_NUMBER() OVER(ORDER BY C.ID ASC) AS ItemNro, C.TipoValor as Tipo, C.ID as IDValor, C.Importe, C.Cotizacion, dbo.CC_ConvertiraMoneda(C.Importe,null,null,C.Cotizacion,@Cotizacion) as ImporteMoneda, C.Cuenta as CajaEntrada, '' as Cuotas, V.Entidad, C.Concepto
		from @IF I
		inner join CG_MovimientosCuentasNuestras C ON C.TipoDocumentoGenera = 23 AND C.GeneraenDocumento = I.ItemID and C.Anulado=0 AND C.MovimientoAnulacion is null and coalesce(C.Pendiente,0)=0
		left join CG_CarteraValores V on V.MovimientoEntradaCaja = C.ID
		where I.Tipo = 2 
		if @@ROWCOUNT >0 begin
   			insert into CC_MovimientosCtaCte(Fecha, Tipo, Titular, IDAfecta, Afecta, Importe , Comentarios,ReferenciaAfecta,
   			IDOrigen,Origen,Anulado,ReferenciaOrigen,Cotizacion,Asignado,RealizadoPor)
   			Select F.Fecha, T.ID , F.CodCli, F.ID, 1, (Select SUM(ImporteMoneda) FROM CG_ValoresRecibo R where R.IDRecibo = -F.ID) * T.Signo ,
   			replace(replace(T.Descripcion,'%N%',F.Numero ),'%C%', F.Cliente),F.Numero, F.ID,T.TipoDocumento,0,F.Numero,F.Cotizacion,0,F.RealizadoPor 
   			FROM CG_Facturas_Tabla F 
   			Inner Join CC_TiposMovimientosCtaCte T on T.TipoDocumento = 13
   			Where F.ID = @ID
		end
   				
   		--Actualizar mov stock
   		update CK_MovimientosStock set Comentarios = Comentarios + @Numero, Comprobante = @Numero, IDFactura = @ID where ID = @MovimientoStock

		if coalesce(@Hidden_SP_AfterUpdate,'')<>'' begin
			exec sp_executesql @Hidden_SP_AfterUpdate, N'@ID int',@ID=@ID
		end
		commit
		if coalesce(@Hidden_SP_AfterCommit,'')<>'' begin
			exec sp_executesql @Hidden_SP_AfterCommit, N'@ID int',@ID=@ID
		end
	end try
	begin catch
		declare @E varchar(4000)=ERROR_MESSAGE()
		if @@TRANCOUNT >0
			rollback
		if coalesce(@Hidden_SP_AfterRollback,'')<>'' begin
			exec sp_executesql @Hidden_SP_AfterRollback
		end
		raiserror (@E,16,1)
	end catch
end

 


(1 rows affected)
