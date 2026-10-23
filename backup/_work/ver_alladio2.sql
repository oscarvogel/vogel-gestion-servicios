SET NOCOUNT ON;

SELECT o.name, o.type_desc, OBJECT_SCHEMA_NAME(o.object_id)
FROM sys.objects o WHERE o.name LIKE '%PoliticasxArea%';

SELECT c.column_id, c.name, TYPE_NAME(c.user_type_id)
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('dbo.CS_PoliticasxArea')
ORDER BY c.column_id;

SELECT REPLACE(REPLACE(definition, CHAR(13), ' '), CHAR(10), ' ')
FROM sys.sql_modules WHERE object_id = OBJECT_ID('dbo.CS_PoliticasxArea');

SELECT name FROM sys.tables WHERE name IN ('Partes','CS_Partes','Aux_PoliticasxArea');
