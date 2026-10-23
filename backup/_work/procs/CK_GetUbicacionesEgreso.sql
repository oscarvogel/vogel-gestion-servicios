CREATE PROCEDURE [dbo].[CK_GetUbicacionesEgreso]
@IDDeposito INT,
@IDArticulo INT
AS
SELECT D.*, Ad.Ubicacion 
FROM CK_Depositos D WITH (NOLOCK)
LEFT JOIN CK_ArticulosxDeposito AD WITH (NOLOCK) ON AD.IDDeposito = D.ID AND AD.IDArticulo = @IDArticulo
WHERE D.ID = @IDDeposito

IF EXISTS(SELECT * FROM CK_Depositos WITH (NOLOCK) WHERE ID = @IDDeposito AND ManejaUbicaciones = 1 AND @IDArticulo > 0)
	SELECT U.ID, U.Ubicacion as Ubicacion, AU.Cantidad, COALESCE(U.Descripcion, '') + CASE WHEN AU.Cantidad > 0 THEN ' EN USO (' ELSE ' Usado (' END + CONVERT(VARCHAR, CONVERT(INT, AU.Cantidad)) + ')' as Descripcion
	FROM CK_ArticulosxUbicacion AU WITH (NOLOCK)
	INNER JOIN CK_Ubicaciones U WITH (NOLOCK) ON U.ID = AU.Ubicacion
	WHERE AU.IDArticulo = @IDArticulo AND U.IDDeposito = @IDDeposito AND AU.Cantidad > 0	-- Las ubicaciones que tienen
	ORDER BY Cantidad DESC, Ubicacion 
ELSE
	SELECT 0 as ID, Ubicacion FROM CK_ArticulosxDeposito WITH (NOLOCK) WHERE IDArticulo = @IDArticulo AND IDDeposito = @IDDeposito

(1 rows affected)
