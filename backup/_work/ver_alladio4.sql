SET NOCOUNT ON;

SELECT 'AUX_ALL_COLUMNS';
SELECT c.column_id, c.name, TYPE_NAME(c.user_type_id)
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('dbo.Aux_PoliticasxArea')
ORDER BY c.column_id;

SELECT 'FULL_VIEW_DEFINITION';
DECLARE @d NVARCHAR(MAX);
SELECT @d = definition FROM sys.sql_modules WHERE object_id = OBJECT_ID('dbo.CS_PoliticasxArea');
DECLARE @i INT = 1;
WHILE @i <= LEN(@d)
BEGIN
    PRINT SUBSTRING(@d, @i, 200);
    SET @i = @i + 200;
END
