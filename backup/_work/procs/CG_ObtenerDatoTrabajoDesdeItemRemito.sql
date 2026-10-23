CREATE Procedure [dbo].[CG_ObtenerDatoTrabajoDesdeItemRemito]
@IDItemRemito int, @TipoDato int = null
AS
set nocount off
DECLARE @Dato VARCHAR(100)
declare @IDTrabajo int

Select @IDTrabajo=pOrden 
FROM cg_itemsRemitos R
INNER JOIN CK_ItemsMovStock M ON M.ID = R.ItemStockRelacionado
Where R.ID = @IDItemRemito

set nocount on

if @IDTrabajo>0 Begin
	SELECT @Dato = CONVERT(VARCHAR(100), @IDTrabajo)
	if @TipoDato=1 --Nro del Agente
		Select @Dato = NroOtorgado From CS_Trabajos Where IDTrabajo = @IDTrabajo

	IF @TipoDato > 1000 BEGIN		
		-- Es el contenido de un campo adicional... Restando 1000 se obtiene el ID del campo Se podria hacer algo con SQL dinamico para devolver cualquier campo
		-- SELECT @Dato = CONVERT(VARCHAR(100), [Fecha Canje], 103) FROM CS_caTrabajos WHERE ID = @IDTrabajo
		DECLARE @Campo VARCHAR(100), @Tipo SMALLINT
		SELECT @Campo = Nombre, @Tipo = TipoDato FROM CC_CamposAdicionales_Definicion WHERE AplicableA = 1 AND ID = @TipoDato - 1000
		IF NOT @Campo IS NULL BEGIN
			-- Tengo el nombre del campo, buscar valor
			DECLARE @Sql NVARCHAR(MAX)
			IF @Tipo = 3
				SET @Sql = 'SELECT @Valor = CONVERT(VARCHAR(MAX), [' + @Campo + '], 103) FROM CS_caTrabajos WHERE ID = ' + CONVERT(VARCHAR(10), @IDTrabajo);
			ELSE
				SET @Sql = 'SELECT @Valor = CONVERT(VARCHAR(MAX), [' + @Campo + ']) FROM CS_caTrabajos WHERE ID = ' + CONVERT(VARCHAR(10), @IDTrabajo);

			EXECUTE sp_executesql @Sql, N'@Valor VARCHAR(MAX) OUTPUT', @Valor = @Dato OUTPUT
		END
	END		

	IF @TipoDato = 10 BEGIN		-- Entre calles de la OS
		SELECT @Dato = COALESCE(Entre, '') + CASE WHEN COALESCE(Entre2, '') <> '' AND COALESCE(Entre, '') <> '' THEN COALESCE(' y ' + Entre2, '') ELSE '' END  FROM CS_Trabajos WHERE IDTrabajo = @IDTrabajo
		IF @Dato <> '' SET @Dato = 'ENTRE ' + @Dato
	END

	SELECT @Dato
end else
	select null --Nada!


(1 rows affected)
