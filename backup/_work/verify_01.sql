SET NOCOUNT ON;
PRINT '=== VERIFICACION: filas de tablas de ubicacion/mesas ===';
SELECT 'CK_ArticulosxUbicacion' AS t, COUNT(*) AS n FROM CK_ArticulosxUbicacion
UNION ALL SELECT 'CK_ArticulosxDeposito', COUNT(*) FROM CK_ArticulosxDeposito
UNION ALL SELECT 'CK_Ubicaciones', COUNT(*) FROM CK_Ubicaciones
UNION ALL SELECT 'CS_Ubicaciones', COUNT(*) FROM CS_Ubicaciones
UNION ALL SELECT 'UBIC_Ubicaciones', COUNT(*) FROM UBIC_Ubicaciones
UNION ALL SELECT 'CS_TipoUbicaciones', COUNT(*) FROM CS_TipoUbicaciones
UNION ALL SELECT 'CS_UbicacionEquipoLog', COUNT(*) FROM CS_UbicacionEquipoLog
UNION ALL SELECT 'dbo.Areas', COUNT(*) FROM dbo.Areas
UNION ALL SELECT 'dbo.TiposTrabajos', COUNT(*) FROM dbo.TiposTrabajos
UNION ALL SELECT 'dbo.CC_TiposCliente', COUNT(*) FROM dbo.CC_TiposCliente
UNION ALL SELECT 'dbo.CC_Tareas', COUNT(*) FROM dbo.CC_Tareas
UNION ALL SELECT 'dbo.CC_Sucursales', COUNT(*) FROM dbo.CC_Sucursales;

PRINT '';
PRINT '=== VERIFICACION: garantia (3 estados) ===';
SELECT Garantia, COUNT(*) AS n FROM CS_Trabajos GROUP BY Garantia ORDER BY n DESC;

PRINT '';
PRINT '=== VERIFICACION: mesas como texto libre en CS_Trabajos.Ubicacion ===';
SELECT TOP 25 Ubicacion, COUNT(*) AS n FROM CS_Trabajos
WHERE Ubicacion IS NOT NULL AND LTRIM(RTRIM(Ubicacion)) <> ''
GROUP BY Ubicacion ORDER BY n DESC;

PRINT '';
PRINT '=== VERIFICACION: TipoDoc de facturas ===';
SELECT TipoDoc, COUNT(*) AS n, MIN(Numero) AS ejemplo_min, MAX(Numero) AS ejemplo_max, MIN(Fecha) AS f_min, MAX(Fecha) AS f_max
FROM CG_Facturas_Tabla GROUP BY TipoDoc;

PRINT '';
PRINT '=== VERIFICACION: tipos de tarea (politica) ===';
SELECT TipoTrabajo, COUNT(*) AS n FROM Aux_PoliticasxArea GROUP BY TipoTrabajo ORDER BY n DESC;

PRINT '';
PRINT '=== VERIFICACION: area = marcas ===';
SELECT TOP 12 Codigo, Area, Empresa, NuestraDenominacion FROM dbo.Areas ORDER BY Codigo;
