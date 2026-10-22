CREATE PROCEDURE [dbo].[CC_ComisionesTrabajos]
@IDUsuario INT,
@Politica nVarchar(4000),
@Estado TINYINT,
@Desde DATETIME,
@Hasta DATETIME,
@Tipo TINYINT=0
AS
DECLARE @Pols INT, @HuboError INT

EXEC @HuboError = sp_xml_preparedocument @Pols OUTPUT, @Politica
IF @HuboError <> 0   RAISERROR ('Formato inválido en XML Politicas', 16, 1)

IF @Tipo = 0 
BEGIN
	SELECT T.IDTrabajo, T.NroOtorgado as Cliente, T.IDPolitica, T.Area, T.Clasificacion,
	COALESCE(I.Persona, P.LiquidaComision) as Persona,
	CASE WHEN P.LiquidaComision = -1 THEN  T.Intervienen ELSE 1 END as Intervienen, 
	P.NumeroParte, P.Descripcion, P.Tipo as Categoria, P.Unitario, P.CostoUnitario,  P.Cotizacion, P.CotizacionCosto,
	P.LiquidaComision, P.Cantidad,
	CASE WHEN @Estado = 7 THEN FechaCerrada ELSE FechaLiquidacion END as Fecha,
	COALESCE(Co.Tipo, CoAg.Tipo, CoD0.Tipo, CoD0Ag.Tipo, CoD1.Tipo, CoD1Ag.Tipo, CoD2.Tipo, CoD2Ag.Tipo, 
	CASE P.Tipo
	WHEN 0 THEN COALESCE(Eu.TipoComisionProducto, EuD0.tipoComisionProducto, EuD1.TipoComisionProducto, EuD2.TipoComisionProducto)
	WHEN 1 THEN COALESCE(Eu.TipoComisionRepuesto, EuD0.tipoComisionRepuesto, EuD1.TipoComisionRepuesto, EuD2.TipoComisionRepuesto)
	WHEN 2 THEN COALESCE(Eu.TipoComisionServicio, EuD0.TipoComisionServicio, EuD1.TipoComisionServicio, EuD2.TipoComisionServicio)
	WHEN 3 THEN COALESCE(Eu.TipoComisionOtros, EuD0.TipoComisionOtros, EuD1.TipoComisionOtros, EuD2.TipoComisionOtros)
	END, 0) as Tipo, 
	COALESCE(Co.Valor, CoAg.Valor, CoD0.Valor, CoD0Ag.Valor, CoD1.Valor, CoD1Ag.Valor, CoD2.Valor, CoD2Ag.Valor, CASE P.Tipo
	WHEN 0 THEN COALESCE(Eu.ValorComisionProducto, EuD0.ValorComisionProducto, EuD1.ValorComisionProducto, EuD2.ValorComisionProducto)
	WHEN 1 THEN COALESCE(Eu.ValorComisionRepuesto, EuD0.ValorComisionRepuesto, EuD1.ValorComisionRepuesto, EuD2.ValorComisionRepuesto)
	WHEN 2 THEN COALESCE(Eu.ValorComisionServicio, EuD0.ValorComisionServicio, EuD1.ValorComisionServicio, EuD2.ValorComisionServicio)
	WHEN 3 THEN COALESCE(Eu.ValorComisionOtros, EuD0.ValorComisionOtros, EuD1.ValorComisionOtros, EuD2.ValorComisionOtros)
	END, 0) as Valor,
	COALESCE(Eu.ID, EuD0.ID, EuD1.ID, EuD2.ID) as EsquemaDefecto
	FROM Partes P
	INNER JOIN CS_Trabajos T ON T.IDTrabajo = P.NroOrden
	LEFT JOIN Intervienen I ON I.Orden = T.IDTrabajo AND P.LiquidaComision = -1
	LEFT JOIN CC_Articulos A ON A.ID = P.ItemID
	LEFT JOIN CC_ComisionxUsuario Cu ON Cu.IDUsuario = COALESCE(I.Persona, P.LiquidaComision) AND Cu.IDPolitica = T.IDPolitica							-- Esquema del usuario y politica
	LEFT JOIN CC_EsquemasComision Eu ON Eu.ID = Cu.IDEsquema
	LEFT JOIN CC_ComisionxUsuario CuD0 ON CuD0.IDUsuario = COALESCE(I.Persona, P.LiquidaComision) And CuD0.IDPolitica = 0 AND Eu.ID IS NULL				-- El Usuario, Todas las politicas
	LEFT JOIN CC_EsquemasComision EuD0 ON EuD0.ID = CuD0.IDEsquema
	LEFT JOIN CC_ComisionxUsuario CuD1 ON CuD1.IDUsuario = 0 And CuD1.IDPolitica = T.IDPolitica AND COALESCE(Eu.ID, EuD0.ID) IS NULL	-- Todos los usuarios, la politica
	LEFT JOIN CC_EsquemasComision EuD1 ON EuD1.ID = CuD1.IDEsquema
	LEFT JOIN CC_ComisionxUsuario CuD2 ON CuD2.IDUsuario = 0 And CuD2.IDPolitica = 0 AND COALESCE(Eu.ID, EuD0.ID, EuD1.ID) IS NULL										-- Todos los usuarios, Todas las politicas
	LEFT JOIN CC_EsquemasComision EuD2 ON EuD2.ID = CuD2.IDEsquema
	LEFT JOIN CC_Comisiones Co ON Co.Esquema = Cu.IDEsquema AND Co.IDArticulo = P.ItemID							-- Comisiones del Esquema del articulo del usuario y la politica
	LEFT JOIN CC_Comisiones CoAg ON CoAg.Esquema = Cu.IDEsquema AND CoAg.IDArticulo = - A.Agrupacion					-- Comisiones del Esquema de la agrupacion del usuario y la politica
	LEFT JOIN CC_Comisiones CoD0 ON CoD0.Esquema = CuD0.IDEsquema AND CoD0.IDArticulo = P.ItemID						-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD0Ag ON CoD0Ag.Esquema = CuD0.IDEsquema AND CoD0Ag.IDArticulo = -A.Agrupacion				-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD1 ON CoD1.Esquema = CuD1.IDEsquema AND CoD1.IDArticulo = P.ItemID						-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD1Ag ON CoD1Ag.Esquema = CuD1.IDEsquema AND CoD1Ag.IDArticulo = -A.Agrupacion				-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD2 ON CoD2.Esquema = CuD2.IDEsquema AND CoD2.IDArticulo = P.ItemID						-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD2Ag ON CoD2Ag.Esquema = CuD2.IDEsquema AND CoD2Ag.IDArticulo = -A.Agrupacion				-- Comisiones del esquema del articulo del usuario, todas las politicas
	WHERE (COALESCE(I.Persona, P.LiquidaComision) = @IDUsuario OR @IDUsuario = 0) 
	AND T.IDPolitica IN (SELECT Politica FROM OPENXML (@Pols, '/R/I', 1) WITH (Politica INT) )
	AND P.LiquidaComision <> 0
	AND CASE @Estado WHEN 7 THEN T.FechaCerrada ELSE T.FechaLiquidacion END >= @Desde
	AND CASE @Estado WHEN 7 THEN T.FechaCerrada ELSE T.FechaLiquidacion END <= @Hasta
	AND COALESCE(Eu.ID, EuD0.ID, EuD1.ID, EuD2.ID) IS NOT NULL
	AND COALESCE(Co.Tipo, CoAg.Tipo, CoD0.Tipo, CoD0Ag.Tipo, CoD1.Tipo, CoD1Ag.Tipo, CoD2.Tipo, CoD2Ag.Tipo,  	CASE P.Tipo		--Excluir 'Sin Comision'
	WHEN 0 THEN COALESCE(Eu.TipoComisionProducto, EuD0.tipoComisionProducto, EuD1.TipoComisionProducto, EuD2.TipoComisionProducto)
	WHEN 1 THEN COALESCE(Eu.TipoComisionRepuesto, EuD0.tipoComisionRepuesto, EuD1.TipoComisionRepuesto, EuD2.TipoComisionRepuesto)
	WHEN 2 THEN COALESCE(Eu.TipoComisionServicio, EuD0.TipoComisionServicio, EuD1.TipoComisionServicio, EuD2.TipoComisionServicio)
	WHEN 3 THEN COALESCE(Eu.TipoComisionOtros, EuD0.TipoComisionOtros, EuD1.TipoComisionOtros, EuD2.TipoComisionOtros)
	END, 0 )  <>0 
	ORDER BY COALESCE(I.Persona, P.LiquidaComision), T.IDPolitica, T.IDTrabajo
END
ELSE
BEGIN
	SELECT T.IDTrabajo, T.NroOtorgado as Cliente, T.IDPolitica, T.Area, T.Clasificacion,
	T.Responsable as Persona,
	1 as Intervienen, 
	P.NumeroParte, P.Descripcion, P.Tipo as Categoria, P.Unitario, P.CostoUnitario,  P.Cotizacion, P.CotizacionCosto,
	P.LiquidaComision, P.Cantidad,
	CASE WHEN @Estado = 7 THEN FechaCerrada ELSE FechaLiquidacion END as Fecha,
	COALESCE(Co.Tipo, CoAg.Tipo, CoD0.Tipo, CoD0Ag.Tipo, CoD1.Tipo, CoD1Ag.Tipo, CoD2.Tipo, CoD2Ag.Tipo, CASE P.Tipo
	WHEN 0 THEN COALESCE(Eu.TipoComisionProducto, EuD0.tipoComisionProducto, EuD1.TipoComisionProducto, EuD2.TipoComisionProducto)
	WHEN 1 THEN COALESCE(Eu.TipoComisionRepuesto, EuD0.tipoComisionRepuesto, EuD1.TipoComisionRepuesto, EuD2.TipoComisionRepuesto)
	WHEN 2 THEN COALESCE(Eu.TipoComisionServicio, EuD0.TipoComisionServicio, EuD1.TipoComisionServicio, EuD2.TipoComisionServicio)
	WHEN 3 THEN COALESCE(Eu.TipoComisionOtros, EuD0.TipoComisionOtros, EuD1.TipoComisionOtros, EuD2.TipoComisionOtros)
	END, 0) as Tipo, 
	COALESCE(Co.Valor, CoAg.Valor, CoD0.Valor, CoD0Ag.Valor, CoD1.Valor, CoD1Ag.Valor, CoD2.Valor, CoD2Ag.Valor, CASE P.Tipo
	WHEN 0 THEN COALESCE(Eu.ValorComisionProducto, EuD0.ValorComisionProducto, EuD1.ValorComisionProducto, EuD2.ValorComisionProducto)
	WHEN 1 THEN COALESCE(Eu.ValorComisionRepuesto, EuD0.ValorComisionRepuesto, EuD1.ValorComisionRepuesto, EuD2.ValorComisionRepuesto)
	WHEN 2 THEN COALESCE(Eu.ValorComisionServicio, EuD0.ValorComisionServicio, EuD1.ValorComisionServicio, EuD2.ValorComisionServicio)
	WHEN 3 THEN COALESCE(Eu.ValorComisionOtros, EuD0.ValorComisionOtros, EuD1.ValorComisionOtros, EuD2.ValorComisionOtros)
	END, 0) as Valor,
	COALESCE(Eu.ID, EuD0.ID, EuD1.ID, EuD2.ID) as EsquemaDefecto
	FROM Partes P
	INNER JOIN CS_Trabajos T ON T.IDTrabajo = P.NroOrden
	LEFT JOIN CC_Articulos A ON A.ID = P.ItemID
	LEFT JOIN CC_ComisionxUsuario Cu ON Cu.IDUsuario = T.Responsable AND Cu.IDPolitica = T.IDPolitica							-- Esquema del usuario y politica
	LEFT JOIN CC_EsquemasComision Eu ON Eu.ID = Cu.IDEsquema
	LEFT JOIN CC_ComisionxUsuario CuD0 ON CuD0.IDUsuario = T.Responsable And CuD0.IDPolitica = 0 AND Eu.ID IS NULL				-- El Usuario, Todas las politicas
	LEFT JOIN CC_EsquemasComision EuD0 ON EuD0.ID = CuD0.IDEsquema
	LEFT JOIN CC_ComisionxUsuario CuD1 ON CuD1.IDUsuario = 0 And CuD1.IDPolitica = T.IDPolitica AND COALESCE(Eu.ID, EuD0.ID) IS NULL	-- Todos los usuarios, la politica
	LEFT JOIN CC_EsquemasComision EuD1 ON EuD1.ID = CuD1.IDEsquema
	LEFT JOIN CC_ComisionxUsuario CuD2 ON CuD2.IDUsuario = 0 And CuD2.IDPolitica = 0 AND COALESCE(Eu.ID, EuD0.ID, EuD1.ID) IS NULL										-- Todos los usuarios, Todas las politicas
	LEFT JOIN CC_EsquemasComision EuD2 ON EuD2.ID = CuD2.IDEsquema
	LEFT JOIN CC_Comisiones Co ON Co.Esquema = Cu.IDEsquema AND Co.IDArticulo = P.ItemID							-- Comisiones del Esquema del articulo del usuario y la politica
	LEFT JOIN CC_Comisiones CoAg ON CoAg.Esquema = Cu.IDEsquema AND CoAg.IDArticulo = - A.Agrupacion					-- Comisiones del Esquema de la agrupacion del usuario y la politica
	LEFT JOIN CC_Comisiones CoD0 ON CoD0.Esquema = CuD0.IDEsquema AND CoD0.IDArticulo = P.ItemID						-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD0Ag ON CoD0Ag.Esquema = CuD0.IDEsquema AND CoD0Ag.IDArticulo = -A.Agrupacion				-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD1 ON CoD1.Esquema = CuD1.IDEsquema AND CoD1.IDArticulo = P.ItemID						-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD1Ag ON CoD1Ag.Esquema = CuD1.IDEsquema AND CoD1Ag.IDArticulo = -A.Agrupacion				-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD2 ON CoD2.Esquema = CuD2.IDEsquema AND CoD2.IDArticulo = P.ItemID						-- Comisiones del esquema del articulo del usuario, todas las politicas
	LEFT JOIN CC_Comisiones CoD2Ag ON CoD2Ag.Esquema = CuD2.IDEsquema AND CoD2Ag.IDArticulo = -A.Agrupacion				-- Comisiones del esquema del articulo del usuario, todas las politicas
	WHERE (T.Responsable = @IDUsuario OR @IDUsuario = 0) 
	AND T.IDPolitica IN (SELECT Politica FROM OPENXML (@Pols, '/R/I', 1) WITH (Politica INT) )
	AND CASE @Estado WHEN 7 THEN T.FechaCerrada ELSE T.FechaLiquidacion END >= @Desde
	AND CASE @Estado WHEN 7 THEN T.FechaCerrada ELSE T.FechaLiquidacion END <= @Hasta
	AND COALESCE(Eu.ID, EuD0.ID, EuD1.ID, EuD2.ID) IS NOT NULL
	AND COALESCE(Co.Tipo, CoAg.Tipo, CoD0.Tipo, CoD0Ag.Tipo, CoD1.Tipo, CoD1Ag.Tipo, CoD2.Tipo, CoD2Ag.Tipo,  	CASE P.Tipo		--Excluir 'Sin Comision'
	WHEN 0 THEN COALESCE(Eu.TipoComisionProducto, EuD0.tipoComisionProducto, EuD1.TipoComisionProducto, EuD2.TipoComisionProducto)
	WHEN 1 THEN COALESCE(Eu.TipoComisionRepuesto, EuD0.tipoComisionRepuesto, EuD1.TipoComisionRepuesto, EuD2.TipoComisionRepuesto)
	WHEN 2 THEN COALESCE(Eu.TipoComisionServicio, EuD0.TipoComisionServicio, EuD1.TipoComisionServicio, EuD2.TipoComisionServicio)
	WHEN 3 THEN COALESCE(Eu.TipoComisionOtros, EuD0.TipoComisionOtros, EuD1.TipoComisionOtros, EuD2.TipoComisionOtros)
	END, 0 )  <>0 
	ORDER BY T.Responsable, T.IDPolitica, T.IDTrabajo
END

(1 rows affected)
