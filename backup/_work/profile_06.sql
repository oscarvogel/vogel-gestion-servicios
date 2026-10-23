SET NOCOUNT ON;

PRINT '=== 41. CATEGORIAS DE EQUIPO: normalizacion ===';
SELECT COUNT(DISTINCT UPPER(LTRIM(RTRIM(Equipo)))) AS valores_equipo_distintos FROM CS_Trabajos
WHERE Equipo IS NOT NULL AND LTRIM(RTRIM(Equipo)) <> '';

PRINT '';
PRINT '=== 42. TOP 60 EQUIPOS (para curar el catalogo) ===';
SELECT TOP 60 UPPER(LTRIM(RTRIM(Equipo))) AS equipo, COUNT(*) AS n,
       SUM(CASE WHEN NroSerie IS NOT NULL AND NroSerie NOT IN ('ILEGIBLE','FALTA','S/N','NO TIENE') THEN 1 ELSE 0 END) AS con_serie
FROM CS_Trabajos WHERE Equipo IS NOT NULL AND LTRIM(RTRIM(Equipo)) <> ''
GROUP BY UPPER(LTRIM(RTRIM(Equipo))) ORDER BY n DESC;

PRINT '';
PRINT '=== 43. CATEGORIA por palabras clave (aproximacion) ===';
SELECT categoria, COUNT(*) AS n FROM (
  SELECT CASE
    WHEN UPPER(Equipo) LIKE '%LAVARROP%' OR UPPER(Equipo) LIKE '%LAVABO%' OR UPPER(Equipo) LIKE '%LAVADORA%' THEN 'LAVADORA'
    WHEN UPPER(Equipo) LIKE '%HELADER%' OR UPPER(Equipo) LIKE '%CONGEL%' OR UPPER(Equipo) LIKE '%FREEZER%' THEN 'HELADERA'
    WHEN UPPER(Equipo) LIKE '%HORNO%' OR UPPER(Equipo) LIKE '%COCINA%' OR UPPER(Equipo) LIKE '%ANAFE%' THEN 'COCINA'
    WHEN UPPER(Equipo) LIKE '%AIRE%' OR UPPER(Equipo) LIKE '%ACONDIC%' OR UPPER(Equipo) LIKE '%CALENT%' THEN 'CLIMATIZACION'
    WHEN UPPER(Equipo) LIKE '%MICRO%' THEN 'MICROONDAS'
    WHEN UPPER(Equipo) LIKE '%TALLER' OR UPPER(Equipo) LIKE '%DEPOSITO' THEN 'INTERNO'
    ELSE 'OTROS' END AS categoria
  FROM CS_Trabajos WHERE Equipo IS NOT NULL AND LTRIM(RTRIM(Equipo)) <> ''
) X GROUP BY categoria ORDER BY n DESC;

PRINT '';
PRINT '=== 44. CONTACTO DEL CLIENTE (telefono) ===';
SELECT c.name, ty.name, c.max_length FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id = OBJECT_ID(N'dbo.CC_ContactosxCliente') ORDER BY c.column_id;
SELECT TOP 5 * FROM dbo.CC_ContactosxCliente;
