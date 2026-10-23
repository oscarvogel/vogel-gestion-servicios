CREATE PROCEDURE [dbo].[CC_OrdenarComisionxUsuario]
AS
UPDATE C SET C.Orden = O.Orden
FROM CC_ComisionxUsuario C 
INNER JOIN (
SELECT Cu.IDUsuario, U.Nombre, CU.IDEsquema, Cu.IDPolitica, ROW_NUMBER() OVER (ORDER BY U.Nombre, E.Esquema, COALESCE(P.NombreCompleto, 'Todas')) as Orden
FROM CC_ComisionxUsuario Cu
INNER JOIN CC_Usuarios U ON U.Codigo = Cu.IDUsuario
INNER JOIN CC_EsquemasComision E ON E.ID = CU.IDEsquema 
LEFT JOIN CS_PoliticasxArea P ON P.ID = Cu.IDPolitica ) O ON O.IDUsuario = C.IDUsuario AND O.IDEsquema = C.IDEsquema AND O.IDPolitica = C.IDPolitica


(1 rows affected)
