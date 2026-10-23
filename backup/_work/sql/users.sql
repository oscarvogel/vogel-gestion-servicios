SET NOCOUNT ON;
-- Usuarios del legacy (dbo.CC_Usuarios) con sus tareas.
-- dbo.CC_Tareas: 1=Facturista 2=Vendedor 3=Tecnico 4=Administrativo 5=Fletero 6=Agente 7=Cajero
-- El PK es Codigo (no ID). La tarea 3 = tecnico, la 2 = vendedor.
SELECT
    CAST(U.Codigo AS VARCHAR(20))             AS codigo,
    REPLACE(REPLACE(REPLACE(U.Nombre, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' ') AS nombre,
    ISNULL(REPLACE(REPLACE(REPLACE(U.EMail, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS email,
    ISNULL(REPLACE(REPLACE(REPLACE(U.Descripcion, NCHAR(13), N' '), NCHAR(10), N' '), N'|', N' '), '') AS descripcion,
    CAST(MAX(CASE WHEN T.Tarea = N'Tecnico'   THEN 1 ELSE 0 END) AS VARCHAR(5)) AS es_tecnico,
    CAST(MAX(CASE WHEN T.Tarea = N'Vendedor'  THEN 1 ELSE 0 END) AS VARCHAR(5)) AS es_vendedor,
    CAST(MAX(CASE WHEN T.Tarea = N'Facturista' THEN 1 ELSE 0 END) AS VARCHAR(5)) AS es_facturista
FROM dbo.CC_Usuarios U
LEFT JOIN dbo.CC_TareasxUsuario TU ON TU.Usuario = U.Codigo
LEFT JOIN dbo.CC_Tareas T ON T.ID = TU.Tarea
GROUP BY U.Codigo, U.Nombre, U.EMail, U.Descripcion
ORDER BY U.Codigo;
