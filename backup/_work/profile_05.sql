SET NOCOUNT ON;

PRINT '=== 34. CONTACTO: tabla de contactos del cliente ===';
SELECT s.name + N'.' + t.name AS tabla FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
WHERE t.name LIKE N'%Contacto%' AND t.is_ms_shipped = 0;
SELECT c.name, ty.name, c.max_length FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id = OBJECT_ID(N'dbo.CC_ContactosDeClientes');

PRINT '';
PRINT '=== 35. TipoTrabajo de las politicas ===';
SELECT TipoTrabajo, COUNT(*) AS n FROM Aux_PoliticasxArea GROUP BY TipoTrabajo ORDER BY n DESC;
SELECT * FROM Aux_PoliticasxArea WHERE TipoTrabajo IS NOT NULL ORDER BY ID;

PRINT '';
PRINT '=== 36. VENDEDOR: distribucion en clientes ===';
SELECT Vendedor, COUNT(*) AS n FROM CC_Clientes_Tabla WHERE Vendedor IS NOT NULL GROUP BY Vendedor ORDER BY n DESC;
SELECT U.Codigo, U.Nombre, U.Descripcion, COUNT(C.CodCli) AS clientes
FROM CC_Usuarios U LEFT JOIN CC_Clientes_Tabla C ON C.Vendedor = U.Codigo
GROUP BY U.Codigo, U.Nombre, U.Descripcion ORDER BY clientes DESC;

PRINT '';
PRINT '=== 37. ROLES (Descripcion) de los usuarios ===';
SELECT ISNULL(Descripcion, N'(sin descripcion)') AS rol, COUNT(*) AS n FROM CC_Usuarios GROUP BY Descripcion ORDER BY n DESC;

PRINT '';
PRINT '=== 38. TECNICOS: usuarios con rol tecnico/taller ===';
SELECT U.Codigo, U.Nombre, U.Descripcion, U.Anulado, U.PermitirLogin,
       (SELECT COUNT(*) FROM Intervienen I WHERE I.Persona = U.Codigo) AS intervenciones,
       (SELECT COUNT(*) FROM CS_Trabajos T WHERE T.Responsable = U.Codigo) AS recibida_como_responsable
FROM CC_Usuarios U
WHERE U.Descripcion LIKE N'%TECNIC%' OR U.Descripcion LIKE N'%Taller%' OR U.Descripcion LIKE N'%MECANIC%'
ORDER BY intervenciones DESC;

PRINT '';
PRINT '=== 39. GARANTIA en CS_Trabajos: distribucion ===';
SELECT Garantia, COUNT(*) AS n FROM CS_Trabajos GROUP BY Garantia ORDER BY n DESC;
SELECT TOP 12 Garantia, DuracionGarantia, COUNT(*) AS n FROM CS_Trabajos GROUP BY Garantia, DuracionGarantia ORDER BY n DESC;

PRINT '';
PRINT '=== 40. VENTA TOTAL por anio (tareas realizadas facturables) ===';
SELECT YEAR(FechaAlta) AS anio, COUNT(*) AS n, SUM(CASE WHEN Estado=8 THEN 1 ELSE 0 END) AS estado8,
       SUM(CASE WHEN VentaTotal>0 THEN VentaTotal ELSE 0 END) AS venta_total,
       SUM(CASE WHEN CostoTotal>0 THEN CostoTotal ELSE 0 END) AS costo_total
FROM CS_Trabajos WHERE YEAR(FechaAlta) >= 2020 GROUP BY YEAR(FechaAlta) ORDER BY anio;
