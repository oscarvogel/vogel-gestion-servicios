CREATE PROCEDURE [dbo].[CC_TraerUsuariosComisiones]
@DesdeModulo INT
AS
SET NOCOUNT ON
IF @DesdeModulo = 0 
	SELECT Codigo, LoginName, Nombre FROM dbo.CC_Usuarios_Visibles('3,6', 0) ORDER BY Nombre	
ELSE 
	SELECT Codigo, LoginName, Nombre FROM dbo.CC_Usuarios_Visibles('2', 0) ORDER BY Nombre

(1 rows affected)
