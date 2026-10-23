CREATE   FUNCTION [dbo].[CS_ListaUsuariosComision](@ListaTareas varchar(2000), @IDSucursal int)
RETURNS TABLE
AS
RETURN (
	SELECT 0 as Codigo, ' [Sin Comisión]' as Nombre, 0 as Anulado
	UNION
	SELECT -1 as Codigo, ' [Para Todos]' as Nombre, 0 as Anulado
	UNION
	SELECT Codigo, Nombre, Anulado FROM CC_NombreUsuario U with (nolock) 
	INNER JOIN dbo.fn_ListaUsuarios(@ListaTareas, @IDSucursal) Tu ON Tu.Usuario = U.Codigo 
	WHERE U.Anulado = 0
)



(1 rows affected)
