CREATE   PROCEDURE [dbo].[CC_ComisionesxEsquema]
@IDEsquema INT,
@Categoria INT = 0,
@Marca INT = 0,
@Orden VARCHAR(20) = 'Descripcion'
AS
SET NOCOUNT ON
DECLARE @Query Varchar(8000)
DECLARE @Esque Varchar(10), @Mar Varchar(10), @Cat Varchar(10)

SET @Esque = CONVERT(Varchar, @IDEsquema)
SET @Mar = CONVERT(Varchar, COALESCE(@Marca, 0))

-- Traer la politica sobre la cual leer...
IF @Marca = 0 AND @Categoria = -1 
   BEGIN				--TODOS
		-- SIN AGRUPACION
		SET @Query = 'SELECT 0 as ID, 0 As Padre, ''<Sin Agrupación>'' as Descripcion, 0 as Orden, 1 as Nivel,
		'''' As Codigo, 
		P.Tipo, P.Valor, 
		0 AS Heredar
		FROM CC_EsquemasComision
		LEFT JOIN CC_Comisiones P ON P.IDArticulo = 0 AND P.Esquema = ' + @Esque + '
		WHERE CC_EsquemasComision.ID = ' + @Esque + '
		UNION
		-- AGRUPACIONES
		SELECT -A.ID as ID, A.Padre, A.Descripcion, CONVERT(DECIMAL(10,2), A.Orden) as Orden, A.Nivel, 
		'''' as Codigo, 
		P.Tipo, P.Valor,
		COALESCE(P.Heredar, 1) as Heredar
		FROM CC_Agrupaciones A
		LEFT JOIN CC_Comisiones P ON P.IDArticulo = -A.ID AND P.Esquema = ' + @Esque + '
		UNION
		-- ARTICULOS (Con propiedades propias o de la agrupacion
		SELECT Ar.ID, Ar.Agrupacion as Padre, Ar.DescripcionReducida as Descripcion, 
		CONVERT(Decimal(10,2), COALESCE(Ag.Orden, 0)) + .1 as Orden, 
		COALESCE(Ag.Nivel, 0) + 1 as Nivel,
		Ar.Codigo,
		COALESCE(Pa.Tipo, Pg.Tipo) as Tipo,
		COALESCE(Pa.Valor, Pg.Valor) as Valor,
		COALESCE(Pa.Heredar, 1) as Heredar
		FROM CC_Articulos Ar
		LEFT JOIN CC_Agrupaciones Ag ON Ag.ID = Ar.Agrupacion
		LEFT JOIN CC_Comisiones Pa ON Pa.IDArticulo = Ar.ID AND Pa.Esquema = ' + @Esque + '
		LEFT JOIN CC_Comisiones Pg ON Pg.IDArticulo = -Ar.Agrupacion AND Pg.Esquema = ' + @Esque + '
		WHERE Ar.Borrado = 0 AND (' + @Mar + ' = 0 OR Ar.Marca = ' + @Mar + ')
		ORDER BY Orden, ' + @Orden

		EXEC (@Query)
   END
ELSE
   BEGIN			-- LOS DE LA MARCA O DE LA CATEGORIA
		DECLARE @ID INT, @FP VARCHAR(255)
		
		DECLARE @Ags Varchar(8000)
		DECLARE @Posicion INT, @c as Varchar(1), @n as Varchar(10)		
		DECLARE Agrupaciones CURSOR LOCAL STATIC FOR 
		SELECT A.ID, A.FULLPATH FROM CC_Agrupaciones A
		WHERE ID IN (SELECT Agrupacion FROM CC_Articulos WHERE Borrado = 0 AND (@Marca = 0 OR Marca = @Marca) AND (@Categoria = -1 OR Categoria = @Categoria))
		OPEN Agrupaciones
		FETCH NEXT FROM Agrupaciones INTO @ID, @FP
		SET @Ags = REPLACE(@FP, '\', ',')
		WHILE @@FETCH_STATUS = 0
		   BEGIN
		      SET @Posicion = 1
		      SET @n = ''		
		      WHILE @Posicion <= DATALENGTH(@FP)
			BEGIN
			   SET @c = SUBSTRING(@FP, @Posicion, 1) 
	                   IF @c <> '\' 
			      SELECT @n = @n + @c
			   ELSE	 
			      BEGIN
				IF @n <> '' AND CHARINDEX(',' + @n + ',', @Ags) = 0 SELECT @Ags = @Ags + @n + ','
			        SET @n = ''
	    		      END
			   SET @Posicion = @Posicion + 1
			END
		      FETCH NEXT FROM Agrupaciones INTO @ID, @FP
		   END
		SET @Ags = LEFT(@Ags, DATALENGTH(@Ags) -1)
		SET @Ags = RIGHT(@Ags, DATALENGTH(@Ags) -1)
		CLOSE Agrupaciones
		DEALLOCATE Agrupaciones
		
	
		-- SIN AGRUPACION
		SET @Cat = CONVERT(Varchar, @Categoria)		
		SET @Ags = COALESCE(@Ags, '0')

		SET @Query = 'SELECT 0 as ID, 0 As Padre, ''Sin Agrupación'' as Descripcion, 0 as Orden, 1 as Nivel,
		'''' As Codigo, 
		P.Tipo, P.Valor, 
		0 AS Heredar
		FROM CC_EsquemasComision
		LEFT JOIN CC_Comisiones P ON P.IDArticulo = 0 AND P.Esquema = ' + @Esque +
		' WHERE CC_EsquemasComision.ID = ' + @Esque + ' AND EXISTS(SELECT * FROM CC_Articulos WHERE Borrado = 0 
		AND (' + @Mar + ' = 0 OR Marca = ' + @Mar + ') 
		AND (' + @Cat + ' = -1 OR Categoria = ' + @Cat + ') 
		AND COALESCE(Agrupacion,0) = 0)
		UNION
		-- AGRUPACIONES
		SELECT -A.ID as ID, A.Padre, A.Descripcion, CONVERT(DECIMAL(10,2), A.Orden) as Orden, A.Nivel, 
		'''' as Codigo, 
		P.Tipo, P.Valor,
		COALESCE(P.Heredar, 1) as Heredar
		FROM CC_Agrupaciones A
		LEFT JOIN CC_Comisiones P ON P.IDArticulo = -A.ID AND P.Esquema = ' + @Esque +
		' WHERE A.ID IN (' + @Ags + ')
		UNION
		-- ARTICULOS (Con propiedades propias o de la agrupacion
		SELECT Ar.ID, Ar.Agrupacion as Padre, Ar.DescripcionReducida as Descripcion, 
		CONVERT(Decimal(10,2), COALESCE(Ag.Orden, 0)) + .1 as Orden, 
		COALESCE(Ag.Nivel, 0) + 1 as Nivel,
		Ar.Codigo,
		COALESCE(Pa.Tipo, Pg.Tipo) as Tipo, 
		COALESCE(Pa.Valor, Pg.Valor) as Valor, 
		COALESCE(Pa.Heredar, 1) as Heredar
		FROM CC_Articulos Ar
		LEFT JOIN CC_Agrupaciones Ag ON Ag.ID = Ar.Agrupacion
		LEFT JOIN CC_Comisiones Pa ON Pa.IDArticulo = Ar.ID AND Pa.Esquema = ' + @Esque + '
		LEFT JOIN CC_Comisiones Pg ON Pg.IDArticulo = -Ar.Agrupacion AND Pg.Esquema = ' + @Esque + '
		WHERE Ar.Borrado = 0 AND (' + @Mar + ' = 0 OR Ar.Marca = ' + @Mar + ') AND (' + @Cat + ' = 0 OR Ar.Categoria = ' + @Cat + ')
		ORDER BY Orden, ' + @Orden
		EXEC (@Query)
   END


(1 rows affected)
