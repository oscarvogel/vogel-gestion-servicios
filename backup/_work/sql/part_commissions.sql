SET NOCOUNT ON;
-- Comision por linea (dbo.CS_ComisionPartexInterviene).
-- ID es el dbo.CS_Partes.ID y IDUsuario es el Codigo de dbo.CC_Usuarios.
SELECT
    CAST(C.ID AS VARCHAR(20))          AS id_parte,
    CAST(C.IDUsuario AS VARCHAR(20))   AS persona,
    CAST(ISNULL(C.Comision, 0) AS VARCHAR(30)) AS comision
FROM dbo.CS_ComisionPartexInterviene C
INNER JOIN dbo.CS_Partes P ON P.ID = C.ID
INNER JOIN dbo.CS_Trabajos T ON T.IDTrabajo = P.NroOrden
WHERE T.FechaAlta >= '20200101'
ORDER BY C.ID, C.IDUsuario;
