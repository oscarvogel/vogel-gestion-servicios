CREATE PROCEDURE [dbo].[CK_GetUbicacionesIngreso]
@IDDeposito INT,
@IDArticulo INT
AS
SELECT D.*, Ad.Ubicacion FROM CK_Depositos D WITH (NOLOCK)
LEFT JOIN CK_ArticulosxDeposito AD WITH (NOLOCK) ON AD.IDDeposito = D.ID AND AD.IDArticulo = @IDArticulo
WHERE D.ID = @IDDeposito

IF EXISTS(SELECT * FROM CK_Depositos WHERE ID = @IDDeposito AND ManejaUbicaciones = 1 AND @IDArticulo > 0)
	SELECT U.ID, U.Ubicacion as Ubicacion, AU.Cantidad, COALESCE(U.Descripcion, '') + CASE WHEN AU.Cantidad > 0 THEN ' EN USO (' ELSE ' Usado (' END + CONVERT(VARCHAR, CONVERT(INT, AU.Cantidad)) + ')' as Descripcion, -(AU.Cantidad + 100) as Orden 
	FROM CK_ArticulosxUbicacion AU WITH (NOLOCK)
	INNER JOIN CK_Ubicaciones U WITH (NOLOCK) ON U.ID = AU.Ubicacion
	WHERE AU.IDArticulo = @IDArticulo AND U.IDDeposito = @IDDeposito
	UNION 
	SELECT U.ID, U.Ubicacion as Ubicacion, 0 as Cantidad, COALESCE(U.Descripcion, '') as Descripcion, 0 as Orden 
	FROM CK_Ubicaciones U WITH (NOLOCK)
	LEFT JOIN CK_ArticulosxUbicacion AU WITH (NOLOCK) ON AU.Ubicacion = U.ID AND AU.IDArticulo = @IDArticulo
	WHERE AU.IDArticulo IS NULL AND U.IDDeposito = @IDDeposito
	ORDER BY Orden ASC, Ubicacion 
ELSE
	SELECT 0 as ID, Ubicacion FROM CK_ArticulosxDeposito WITH (NOLOCK) WHERE IDArticulo = @IDArticulo AND IDDeposito = @IDDeposito

(1 rows affected)
