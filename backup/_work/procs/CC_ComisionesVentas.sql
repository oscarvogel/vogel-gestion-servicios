CREATE PROCEDURE [dbo].[CC_ComisionesVentas]
@IDUsuario INT,
@Desde DATETIME,
@Hasta DATETIME,
@Incluir INT = 1,	-- 1=Cobradas 0=Todas
@Politica INT = 0	-- Segun Tabla CC_PoliticasComisionVendedor
AS

--@Politica
--0 Cualquiera
--1	Vendedor del comprobante
--2	Vendedor del Cliente
--3	Vendedor del cliente y del comprobante

-- Facturas del vendedor del comprobante
SELECT F.Numero as  IDTrabajo, F.Cliente, 
COALESCE(IFa.Vendedor, F.Vendedor) as Persona,
1 as Intervienen, 
COALESCE(A.Codigo, '') as NumeroParte, COALESCE(A.DescripcionReducida, IFa.Descripcion) as Descripcion, COALESCE(A.Categoria, IFa.SubTipo -1) as Categoria, dbo.CG_ValorItemConDtos(F.ID, 1, IFa.Venta) as Unitario, IFa.Costo as CostoUnitario,  
IFa.Cotizacion, IFa.CotizacionCosto,
1 as LiquidaComision, IFa.Cantidad,
F.Fecha,
COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
								WHEN 0 THEN E.TipoComisionProducto
								WHEN 1 THEN E.TipoComisionRepuesto
								WHEN 2 THEN E.TipoComisionServicio
								WHEN 3 THEN E.TipoComisionOtros
								END, 0) as Tipo, 
COALESCE(Co.Valor, CoAg.Valor, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
									WHEN 0 THEN E.ValorComisionProducto
									WHEN 1 THEN E.ValorComisionRepuesto
									WHEN 2 THEN E.ValorComisionServicio
									WHEN 3 THEN E.ValorComisionOtros
								END, 0) as Valor,
E.ID as EsquemaDefecto,
Cu.IDPolitica,
IFa.ItemNro,
E.Esquema
FROM CG_ItemsFacturas IFa WITH (NOLOCK)
INNER JOIN CG_Facturas F WITH (NOLOCK) ON F.ID = IFa.Identificador
INNER JOIN CC_Clientes_Tabla Cl WITH (NOLOCK) ON Cl.CodCli = F.CodCli
LEFT JOIN CG_SaldosFacturas SF WITH (NOLOCK) ON SF.ID = F.ID
LEFT JOIN CC_Articulos A WITH (NOLOCK) ON A.ID = IFa.ItemID
INNER JOIN CC_ComisionxUsuario Cu WITH (NOLOCK) ON Cu.ID = dbo.CC_EsquemaComisionVenta(COALESCE(IFa.Vendedor, F.Vendedor), 1)									-- Esquema de Comision
INNER JOIN CC_EsquemasComision E WITH (NOLOCK) ON E.ID = Cu.IDEsquema
LEFT JOIN CC_Comisiones Co WITH (NOLOCK)ON Co.Esquema = E.ID AND Co.IDArticulo = A.ID																		-- Comision del articulo
LEFT JOIN CC_Comisiones CoAg WITH (NOLOCK) ON CoAg.Esquema = E.ID AND CoAg.IDArticulo = COALESCE(-A.Agrupacion, 0) AND A.ID > 0								-- Comision de la agrupación del articulo
WHERE IFa.Tipo = 0 
AND COALESCE(IFa.Vendedor, F.Vendedor, 0) <> COALESCE(Cl.Vendedor, 0) AND COALESCE(IFa.Vendedor, F.Vendedor, 0) > 0 							-- Vendedor del comprobante
AND ((@Politica = CU.IDPolitica OR @Politica = 0) AND (COALESCE(IFa.Vendedor, F.Vendedor) = @IDUsuario OR @IDUsuario = 0))						-- Pide cuando es vendedor del comprobante
AND SF.Fecha >= @Desde
AND SF.Fecha <= @Hasta
AND (@Incluir = 0 OR (@Incluir = 1 AND SF.Saldo = 0 ))
AND COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1) WHEN 0 THEN E.TipoComisionProducto WHEN 1 THEN E.TipoComisionRepuesto WHEN 2 THEN E.TipoComisionServicio WHEN 3 THEN E.TipoComisionOtros END, 0) <> 0 

UNION ALL

-- Facturas del vendedor del cliente
SELECT F.Numero as  IDTrabajo, F.Cliente, 
Cl.Vendedor as Persona,
1 as Intervienen, 
COALESCE(A.Codigo, '') as NumeroParte, COALESCE(A.DescripcionReducida, IFa.Descripcion) as Descripcion, COALESCE(A.Categoria, IFa.SubTipo - 1) as Categoria, dbo.CG_ValorItemConDtos(F.ID, 1, IFa.Venta) as Unitario, IFa.Costo as CostoUnitario,  
IFa.Cotizacion, IFa.CotizacionCosto,
1 as LiquidaComision, IFa.Cantidad,
F.Fecha,
COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
								WHEN 0 THEN E.TipoComisionProducto
								WHEN 1 THEN E.TipoComisionRepuesto
								WHEN 2 THEN E.TipoComisionServicio
								WHEN 3 THEN E.TipoComisionOtros
								END, 0) as Tipo, 
COALESCE(Co.Valor, CoAg.Valor, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
									WHEN 0 THEN E.ValorComisionProducto
									WHEN 1 THEN E.ValorComisionRepuesto
									WHEN 2 THEN E.ValorComisionServicio
									WHEN 3 THEN E.ValorComisionOtros
								END, 0) as Valor,
E.ID as EsquemaDefecto,
Cu.IDPolitica,
IFa.ItemNro,
E.Esquema
FROM CG_ItemsFacturas IFa WITH (NOLOCK)
INNER JOIN CG_Facturas F WITH (NOLOCK) ON F.ID = IFa.Identificador
INNER JOIN CC_Clientes_Tabla Cl WITH (NOLOCK) ON Cl.CodCli = F.CodCli
LEFT JOIN CG_SaldosFacturas SF ON SF.ID = F.ID
LEFT JOIN CC_Articulos A WITH (NOLOCK) ON A.ID = IFa.ItemID
INNER JOIN CC_ComisionxUsuario Cu WITH (NOLOCK) ON Cu.ID =  dbo.CC_EsquemaComisionVenta(Cl.Vendedor, 2)									-- Esquema de Comision
INNER JOIN CC_EsquemasComision E WITH (NOLOCK) ON E.ID = Cu.IDEsquema
LEFT JOIN CC_Comisiones Co WITH (NOLOCK) ON Co.Esquema = E.ID AND Co.IDArticulo = A.ID															-- Comision del articulo
LEFT JOIN CC_Comisiones CoAg WITH (NOLOCK) ON CoAg.Esquema = E.ID AND CoAg.IDArticulo = COALESCE(-A.Agrupacion, 0) AND A.ID > 0					-- Comision de la agrupación del articulo
WHERE IFa.Tipo = 0 
AND COALESCE(IFa.Vendedor, F.Vendedor) <> Cl.Vendedor	-- Vendedor del comprobante
AND ((@Politica = CU.IDPolitica OR @Politica = 0) AND (Cl.Vendedor = @IDUsuario OR @IDUsuario = 0))										-- Pide cuando es vendedor del comprobante
AND SF.Fecha >= @Desde
AND SF.Fecha <= @Hasta
AND (@Incluir = 0 OR (@Incluir = 1 AND SF.Saldo = 0 ))
AND COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1) WHEN 0 THEN E.TipoComisionProducto WHEN 1 THEN E.TipoComisionRepuesto WHEN 2 THEN E.TipoComisionServicio WHEN 3 THEN E.TipoComisionOtros END, 0) <> 0

UNION ALL

-- Facturas del vendedor del cliente y del vendedor del comprobante
SELECT F.Numero as  IDTrabajo, F.Cliente, 
COALESCE(IFa.Vendedor, F.Vendedor) as Persona,
1 as Intervienen, 
COALESCE(A.Codigo, '') as NumeroParte, COALESCE(A.DescripcionReducida, IFa.Descripcion) as Descripcion, COALESCE(A.Categoria, IFa.SubTipo - 1) as Categoria, dbo.CG_ValorItemConDtos(F.ID, 1, IFa.Venta) as Unitario, IFa.Costo as CostoUnitario,  
IFa.Cotizacion, IFa.CotizacionCosto,
1 as LiquidaComision, IFa.Cantidad,
F.Fecha,
COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
								WHEN 0 THEN E.TipoComisionProducto
								WHEN 1 THEN E.TipoComisionRepuesto
								WHEN 2 THEN E.TipoComisionServicio
								WHEN 3 THEN E.TipoComisionOtros
								END, 0) as Tipo, 
COALESCE(Co.Valor, CoAg.Valor, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
									WHEN 0 THEN E.ValorComisionProducto
									WHEN 1 THEN E.ValorComisionRepuesto
									WHEN 2 THEN E.ValorComisionServicio
									WHEN 3 THEN E.ValorComisionOtros
								END, 0) as Valor,
E.ID as EsquemaDefecto,
Cu.IDPolitica,
IFa.ItemNro,
E.Esquema
FROM CG_ItemsFacturas IFa
INNER JOIN CG_Facturas F WITH (NOLOCK) ON F.ID = IFa.Identificador
INNER JOIN CC_Clientes_Tabla Cl WITH (NOLOCK) ON Cl.CodCli = F.CodCli
LEFT JOIN CG_SaldosFacturas SF WITH (NOLOCK) ON SF.ID = F.ID
LEFT JOIN CC_Articulos A WITH (NOLOCK) ON A.ID = IFa.ItemID
INNER JOIN CC_ComisionxUsuario Cu WITH (NOLOCK) ON Cu.ID = dbo.CC_EsquemaComisionVenta(Cl.Vendedor, 3) 									-- Esquema de Comision
INNER JOIN CC_EsquemasComision E WITH (NOLOCK) ON E.ID = Cu.IDEsquema
LEFT JOIN CC_Comisiones Co WITH (NOLOCK) ON Co.Esquema = E.ID AND Co.IDArticulo = A.ID															-- Comision del articulo
LEFT JOIN CC_Comisiones CoAg WITH (NOLOCK) ON CoAg.Esquema = E.ID AND CoAg.IDArticulo = COALESCE(-A.Agrupacion, 0) AND A.ID > 0					-- Comision de la agrupación del articulo
WHERE IFa.Tipo = 0
AND COALESCE(IFa.Vendedor, F.Vendedor) = Cl.Vendedor	-- Vendedor del comprobante
AND ((@Politica = CU.IDPolitica OR @Politica = 0) AND ((COALESCE(IFa.Vendedor, F.Vendedor) = @IDUsuario AND Cl.Vendedor = @IDUsuario) OR @IDUsuario = 0))	-- Pide cuando es vendedor del cliente y vendedor del comprobante
AND SF.Fecha >= @Desde
AND SF.Fecha <= @Hasta
AND (@Incluir = 0 OR (@Incluir = 1 AND SF.Saldo = 0 ))
AND COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1) WHEN 0 THEN E.TipoComisionProducto WHEN 1 THEN E.TipoComisionRepuesto WHEN 2 THEN E.TipoComisionServicio WHEN 3 THEN E.TipoComisionOtros END, 0) <> 0 

UNION ALL

-- Creditos del vendedor del comprobante
SELECT F.Numero as  IDTrabajo, F.Cliente, 
COALESCE(IFa.Vendedor, F.Vendedor) as Persona,
1 as Intervienen, 
COALESCE(A.Codigo, '') as NumeroParte, COALESCE(A.DescripcionReducida, IFa.Descripcion) as Descripcion, COALESCE(A.Categoria, IFa.SubTipo - 1) as Categoria, -dbo.CG_ValorItemConDtos(F.ID, 1, IFa.Venta) as Unitario, -IFa.Costo as CostoUnitario,  
IFa.Cotizacion, IFa.CotizacionCosto,
1 as LiquidaComision, IFa.Cantidad,
F.Fecha,
COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
								WHEN 0 THEN E.TipoComisionProducto
								WHEN 1 THEN E.TipoComisionRepuesto
								WHEN 2 THEN E.TipoComisionServicio
								WHEN 3 THEN E.TipoComisionOtros
								END, 0) as Tipo, 
COALESCE(Co.Valor, CoAg.Valor, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
									WHEN 0 THEN E.ValorComisionProducto
									WHEN 1 THEN E.ValorComisionRepuesto
									WHEN 2 THEN E.ValorComisionServicio
									WHEN 3 THEN E.ValorComisionOtros
								END, 0) as Valor,
E.ID as EsquemaDefecto,
Cu.IDPolitica,
IFa.ItemNro,
E.Esquema
FROM CG_ItemsCreditos IFa
INNER JOIN CG_Creditos F WITH (NOLOCK) ON F.ID = IFa.Identificador
INNER JOIN CC_Clientes_Tabla Cl WITH (NOLOCK) ON Cl.CodCli = F.CodCli
LEFT JOIN CC_Articulos A WITH (NOLOCK) ON A.ID = IFa.ItemID
INNER JOIN CC_ComisionxUsuario Cu WITH (NOLOCK) ON Cu.ID = dbo.CC_EsquemaComisionVenta(COALESCE(IFa.Vendedor, F.Vendedor), 1)									-- Esquema de Comision
INNER JOIN CC_EsquemasComision E WITH (NOLOCK) ON E.ID = Cu.IDEsquema
LEFT JOIN CC_Comisiones Co WITH (NOLOCK) ON Co.Esquema = E.ID AND Co.IDArticulo = A.ID															-- Comision del articulo
LEFT JOIN CC_Comisiones CoAg WITH (NOLOCK) ON CoAg.Esquema = E.ID AND CoAg.IDArticulo = COALESCE(-A.Agrupacion, 0) AND A.ID > 0					-- Comision de la agrupación del articulo
LEFT JOIN CG_Facturas_Tabla Fr WITH (NOLOCK) ON F.TipoDocAsociado = 6 AND Fr.ID = F.IDDocAsociado
LEFT JOIN CG_SaldosFacturas Sfr WITH (NOLOCK) ON Sfr.ID = Fr.ID
WHERE IFa.Tipo = 0 
AND COALESCE(IFa.Vendedor, F.Vendedor, 0) <> COALESCE(Cl.Vendedor, 0) AND COALESCE(IFa.Vendedor, F.Vendedor, 0) > 0 								-- Vendedor del comprobante
AND ((@Politica = CU.IDPolitica OR @Politica = 0) AND (COALESCE(IFa.Vendedor, F.Vendedor) = @IDUsuario OR @IDUsuario = 0))									-- Pide cuando es vendedor del comprobante
AND F.Fecha >= @Desde
AND F.Fecha <= @Hasta
AND (@Incluir = 0 OR (@Incluir = 1 AND COALESCE(Sfr.Saldo, 0) = 0 ))
--AND (((@Incluir & 1) = 1 AND F.Estado = 100)  OR ((@Incluir & 2) = 2 AND F.Estado = 0))
AND COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1) WHEN 0 THEN E.TipoComisionProducto WHEN 1 THEN E.TipoComisionRepuesto WHEN 2 THEN E.TipoComisionServicio WHEN 3 THEN E.TipoComisionOtros END, 0) <> 0 

UNION ALL

-- Creditos del vendedor del cliente
SELECT F.Numero as  IDTrabajo, F.Cliente, 
Cl.Vendedor as Persona,
1 as Intervienen, 
COALESCE(A.Codigo, '') as NumeroParte, COALESCE(A.DescripcionReducida, IFa.Descripcion) as Descripcion, COALESCE(A.Categoria, IFa.SubTipo - 1) as Categoria, -dbo.CG_ValorItemConDtos(F.ID, 1, IFa.Venta) as Unitario, -IFa.Costo as CostoUnitario,  
IFa.Cotizacion, IFa.CotizacionCosto,
1 as LiquidaComision, IFa.Cantidad,
F.Fecha,
COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
								WHEN 0 THEN E.TipoComisionProducto
								WHEN 1 THEN E.TipoComisionRepuesto
								WHEN 2 THEN E.TipoComisionServicio
								WHEN 3 THEN E.TipoComisionOtros
								END, 0) as Tipo, 
COALESCE(Co.Valor, CoAg.Valor, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
									WHEN 0 THEN E.ValorComisionProducto
									WHEN 1 THEN E.ValorComisionRepuesto
									WHEN 2 THEN E.ValorComisionServicio
									WHEN 3 THEN E.ValorComisionOtros
								END, 0) as Valor,
E.ID as EsquemaDefecto,
Cu.IDPolitica,
IFa.ItemNro,
E.Esquema
FROM CG_ItemsCreditos IFa WITH (NOLOCK)
INNER JOIN CG_Creditos F WITH (NOLOCK) ON F.ID = IFa.Identificador
INNER JOIN CC_Clientes_Tabla Cl WITH (NOLOCK) ON Cl.CodCli = F.CodCli
LEFT JOIN CC_Articulos A WITH (NOLOCK) ON A.ID = IFa.ItemID
INNER JOIN CC_ComisionxUsuario Cu WITH (NOLOCK) ON Cu.ID = dbo.CC_EsquemaComisionVenta(Cl.Vendedor, 2)									-- Esquema de Comision
INNER JOIN CC_EsquemasComision E WITH (NOLOCK) ON E.ID = Cu.IDEsquema
LEFT JOIN CC_Comisiones Co WITH (NOLOCK) ON Co.Esquema = E.ID AND Co.IDArticulo = A.ID															-- Comision del articulo
LEFT JOIN CC_Comisiones CoAg WITH (NOLOCK) ON CoAg.Esquema = E.ID AND CoAg.IDArticulo = COALESCE(-A.Agrupacion, 0) AND A.ID > 0					-- Comision de la agrupación del articulo
LEFT JOIN CG_Facturas_Tabla Fr WITH (NOLOCK) ON F.TipoDocAsociado = 6 AND Fr.ID = F.IDDocAsociado
LEFT JOIN CG_SaldosFacturas Sfr WITH (NOLOCK) ON Sfr.ID = Fr.ID
WHERE IFa.Tipo = 0 
AND COALESCE(IFa.Vendedor, F.Vendedor) <> Cl.Vendedor	-- Vendedor del comprobante
AND ((@Politica = CU.IDPolitica OR @Politica = 0) AND (Cl.Vendedor = @IDUsuario OR @IDUsuario = 0))										-- Pide cuando es vendedor del comprobante
AND F.Fecha >= @Desde
AND F.Fecha <= @Hasta
AND (@Incluir = 0 OR (@Incluir = 1 AND COALESCE(Sfr.Saldo, 0) = 0 ))
--AND (((@Incluir & 1) = 1 AND F.Estado = 100)  OR ((@Incluir & 2) = 2 AND F.Estado = 0))
AND COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1) WHEN 0 THEN E.TipoComisionProducto WHEN 1 THEN E.TipoComisionRepuesto WHEN 2 THEN E.TipoComisionServicio WHEN 3 THEN E.TipoComisionOtros END, 0) <> 0

UNION ALL

-- Creditos del vendedor del cliente y del vendedor del comprobante
SELECT F.Numero as  IDTrabajo, F.Cliente, 
COALESCE(IFa.Vendedor, F.Vendedor) as Persona,
1 as Intervienen, 
COALESCE(A.Codigo, '') as NumeroParte, COALESCE(A.DescripcionReducida, IFa.Descripcion) as Descripcion, COALESCE(A.Categoria, IFa.SubTipo - 1) as Categoria, -dbo.CG_ValorItemConDtos(F.ID, 1, IFa.Venta) as Unitario, -IFa.Costo as CostoUnitario,  
IFa.Cotizacion, IFa.CotizacionCosto,
1 as LiquidaComision, IFa.Cantidad,
F.Fecha,
COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
								WHEN 0 THEN E.TipoComisionProducto
								WHEN 1 THEN E.TipoComisionRepuesto
								WHEN 2 THEN E.TipoComisionServicio
								WHEN 3 THEN E.TipoComisionOtros
								END, 0) as Tipo, 
COALESCE(Co.Valor, CoAg.Valor, CASE COALESCE(A.Categoria, IFa.SubTipo - 1)
									WHEN 0 THEN E.ValorComisionProducto
									WHEN 1 THEN E.ValorComisionRepuesto
									WHEN 2 THEN E.ValorComisionServicio
									WHEN 3 THEN E.ValorComisionOtros
								END, 0) as Valor,
E.ID as EsquemaDefecto,
Cu.IDPolitica,
IFa.ItemNro,
E.Esquema
FROM CG_ItemsCreditos IFa
INNER JOIN CG_Creditos F WITH (NOLOCK) ON F.ID = IFa.Identificador
INNER JOIN CC_Clientes_Tabla Cl WITH (NOLOCK) ON Cl.CodCli = F.CodCli
LEFT JOIN CC_Articulos A WITH (NOLOCK) ON A.ID = IFa.ItemID
INNER JOIN CC_ComisionxUsuario Cu WITH (NOLOCK) ON Cu.ID = dbo.CC_EsquemaComisionVenta(Cl.Vendedor, 3)									-- Esquema de Comision
INNER JOIN CC_EsquemasComision E WITH (NOLOCK) ON E.ID = Cu.IDEsquema
LEFT JOIN CC_Comisiones Co WITH (NOLOCK) ON Co.Esquema = E.ID AND Co.IDArticulo = A.ID															-- Comision del articulo
LEFT JOIN CC_Comisiones CoAg WITH (NOLOCK) ON CoAg.Esquema = E.ID AND CoAg.IDArticulo = COALESCE(-A.Agrupacion, 0) AND A.ID > 0					-- Comision de la agrupación del articulo
LEFT JOIN CG_Facturas_Tabla Fr WITH (NOLOCK) ON F.TipoDocAsociado = 6 AND Fr.ID = F.IDDocAsociado
LEFT JOIN CG_SaldosFacturas Sfr WITH (NOLOCK) ON Sfr.ID = Fr.ID
WHERE IFa.Tipo = 0
AND COALESCE(IFa.Vendedor, F.Vendedor) = Cl.Vendedor	-- Vendedor del comprobante
AND ((@Politica = CU.IDPolitica OR @Politica = 0) AND ((COALESCE(IFa.Vendedor, F.Vendedor) = @IDUsuario AND Cl.Vendedor = @IDUsuario) OR @IDUsuario = 0))	-- Pide cuando es vendedor del cliente y vendedor del comprobante
AND F.Fecha >= @Desde
AND F.Fecha <= @Hasta
AND (@Incluir = 0 OR (@Incluir = 1 AND COALESCE(Sfr.Saldo, 0) = 0 ))
--AND (((@Incluir & 1) = 1 AND F.Estado = 100)  OR ((@Incluir & 2) = 2 AND F.Estado = 0))
AND COALESCE(Co.Tipo, CoAg.Tipo, CASE COALESCE(A.Categoria, IFa.SubTipo - 1) WHEN 0 THEN E.TipoComisionProducto WHEN 1 THEN E.TipoComisionRepuesto WHEN 2 THEN E.TipoComisionServicio WHEN 3 THEN E.TipoComisionOtros END, 0) <> 0 
ORDER BY Persona, IDPolitica, IDTrabajo, ItemNro

(1 rows affected)
