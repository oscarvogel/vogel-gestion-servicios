SET NOCOUNT ON;

PRINT '=== 1. CC_ComisionxUsuario (esquema por vendedor) ===';
SELECT * FROM dbo.CC_ComisionxUsuario;

PRINT '';
PRINT '=== 2. CC_PoliticasComisionVendedor ===';
SELECT c.name, ty.name, c.max_length FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id=OBJECT_ID(N'dbo.CC_PoliticasComisionVendedor') ORDER BY c.column_id;
SELECT * FROM dbo.CC_PoliticasComisionVendedor;

PRINT '';
PRINT '=== 3. Funcion CC_EsquemaComisionVenta ===';
SELECT OBJECT_DEFINITION(OBJECT_ID(N'dbo.CC_EsquemaComisionVenta'));

PRINT '';
PRINT '=== 4. CC_EsquemasComision: catalogo de esquemas ===';
SELECT c.name, ty.name, c.max_length FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id=OBJECT_ID(N'dbo.CC_EsquemasComision') ORDER BY c.column_id;
SELECT * FROM dbo.CC_EsquemasComision;

PRINT '';
PRINT '=== 5. Quien CONSUME CC_ComisionesVentas (donde se calcula el importe) ===';
SELECT o.name, o.type_desc FROM sys.objects o
JOIN sys.sql_modules m ON m.object_id = o.object_id
WHERE m.definition LIKE '%CC_ComisionesVentas%';

PRINT '';
PRINT '=== 6. CC_Comisiones: el % por articulo/esquema (muestra) ===';
SELECT TOP 15 * FROM dbo.CC_Comisiones ORDER BY 1;

PRINT '';
PRINT '=== 7. Vendedor de las facturas y de los clientes: cruce ===';
SELECT COUNT(*) AS facturas,
       SUM(CASE WHEN F.Vendedor IS NOT NULL AND F.Vendedor > 0 THEN 1 ELSE 0 END) AS con_vendedor_en_factura,
       SUM(CASE WHEN Cl.Vendedor IS NOT NULL AND Cl.Vendedor > 0 THEN 1 ELSE 0 END) AS cliente_con_vendedor,
       SUM(CASE WHEN F.Vendedor = Cl.Vendedor AND F.Vendedor > 0 THEN 1 ELSE 0 END) AS mismo_vendedor
FROM dbo.CG_Facturas_Tabla F
LEFT JOIN dbo.CC_Clientes_Tabla Cl ON Cl.CodCli = F.CodCli;

PRINT '';
PRINT '=== 8. Vendedor por anio (cuanto vende cada uno) ===';
SELECT TOP 15 F.Vendedor, COUNT(*) AS facturas, SUM(F.Total) AS total
FROM dbo.CG_Facturas_Tabla F
WHERE F.Vendedor IS NOT NULL AND F.Vendedor > 0
GROUP BY F.Vendedor ORDER BY total DESC;
