
create Procedure CC_ObtenerDatosImpFacturacion
@Impuesto INT OUT, 
@CatxDef INT OUT, 
@TasaxDef INT OUT
AS
--PARA IMPUESTO IVA!
Select @Impuesto = 1, @TasaxDef=null, @CatxDef=null
--Tasa por defecto
select @TasaxDef=convert(int,convert(varchar(10),DatoAlfa)) From CC_ConfigData Where Propiedad = 'IVA_TasaDefecto'
if coalesce(@TasaxDef,0)=0 set @TasaxDef=1
--Categoría por defecto
select @CatxDef=convert(int,convert(varchar(10),DatoAlfa)) From CC_ConfigData Where Propiedad = 'IVA_CategoriaDefecto'
if coalesce(@CatxDef,0) =0 set @CatxDef=1




(1 rows affected)
