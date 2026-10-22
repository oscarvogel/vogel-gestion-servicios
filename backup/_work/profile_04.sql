SET NOCOUNT ON;

PRINT '=== 28. QUE SON LOS TRABAJOS CON CodCli = 0 ===';
SELECT TOP 8 IDTrabajo, Estado, FechaAlta, Cliente, Equipo, Falla, VentaTotal, TotalPresupuesto, TrabajoRealizado, Sucursal, Intervienen, Responsable
FROM CS_Trabajos WHERE CodCli = 0 AND Estado = 8 ORDER BY FechaAlta DESC;
SELECT Estado, COUNT(*) AS n FROM CS_Trabajos WHERE CodCli = 0 GROUP BY Estado ORDER BY n DESC;

PRINT '';
PRINT '=== 29. COLUMNAS DE Aux_PoliticasxArea ===';
SELECT c.name, ty.name, c.max_length, c.is_nullable FROM sys.columns c
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.Aux_PoliticasxArea') ORDER BY c.column_id;

PRINT '';
PRINT '=== 30. CC_Usuarios: columnas y muestra ===';
SELECT c.name, ty.name, c.max_length FROM sys.columns c
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.CC_Usuarios') ORDER BY c.column_id;
SELECT TOP 44 * FROM CC_Usuarios;

PRINT '';
PRINT '=== 31. Intervienen.Persona == CC_Usuarios ? ===';
SELECT COUNT(*) AS intervenores_distintos FROM (SELECT DISTINCT Persona FROM Intervienen) X;
SELECT TOP 10 Persona, COUNT(*) AS n FROM Intervienen GROUP BY Persona ORDER BY n DESC;

PRINT '';
PRINT '=== 32. CC_Clientes_Tabla.Tipo: nombres de muestra ===';
SELECT Tipo, COUNT(*) AS n, MIN(Cliente) AS ejemplo_1, MAX(Cliente) AS ejemplo_2
FROM CC_Clientes_Tabla GROUP BY Tipo ORDER BY n DESC;
SELECT TOP 12 CodCli, Cliente, Tipo, Vendedor, Liquidar, ServiciosGarantia, CondicionVenta, IDLocalidad, NuestroCodigo
FROM CC_Clientes_Tabla WHERE Cliente LIKE '%S.A%' OR Cliente LIKE '%LTDA%' OR Cliente LIKE '%S.R.L%' ORDER BY Cliente;

PRINT '';
PRINT '=== 33. CONTACTO: como se guarda el telefono del cliente ===';
SELECT c.name, ty.name FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.CC_Contactos') OR c.object_id = OBJECT_ID('dbo.CC_ClientesContactos');
SELECT TOP 5 * FROM dbo.CC_Contactos;
