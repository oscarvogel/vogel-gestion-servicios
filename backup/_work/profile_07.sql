SET NOCOUNT ON;

PRINT '=== 45. CONTACTOS: cobertura ===';
SELECT COUNT(*) AS filas,
       COUNT(DISTINCT CodCli) AS clientes_con_contacto,
       SUM(CASE WHEN Telefono IS NOT NULL AND LTRIM(RTRIM(Telefono)) <> '' AND LTRIM(RTRIM(Telefono)) <> 'NO TIENE' THEN 1 ELSE 0 END) AS con_telefono_real,
       SUM(CASE WHEN Mail IS NOT NULL AND LTRIM(RTRIM(Mail)) <> '' AND LTRIM(RTRIM(Mail)) <> 'NO TIENE' THEN 1 ELSE 0 END) AS con_mail_real
FROM CC_ContactosxCliente;

PRINT '';
PRINT '=== 46. CONTACTOS: top valores de Telefono (placeholders) ===';
SELECT TOP 8 Telefono, COUNT(*) AS n FROM CC_ContactosxCliente GROUP BY Telefono ORDER BY n DESC;

PRINT '';
PRINT '=== 47. CLIENTE: telefono directo vs contacto ===';
SELECT COUNT(*) AS clientes,
       SUM(CASE WHEN Telefonos IS NOT NULL AND LTRIM(RTRIM(Telefonos)) <> '' AND LTRIM(RTRIM(Telefonos)) <> 'NO TIENE' THEN 1 ELSE 0 END) AS con_telefono_en_cliente,
       SUM(CASE WHEN Email IS NOT NULL AND LTRIM(RTRIM(Email)) <> '' AND LTRIM(RTRIM(Email)) <> 'NO TIENE' THEN 1 ELSE 0 END) AS con_email_en_cliente
FROM CC_Clientes_Tabla;

PRINT '';
PRINT '=== 48. CONTACTO PRINCIPAL: cuantos clientes tienen y son validos ===';
SELECT COUNT(*) AS clientes,
       SUM(CASE WHEN CP.ID IS NOT NULL THEN 1 ELSE 0 END) AS con_contacto_principal,
       SUM(CASE WHEN CP.Telefono IS NOT NULL AND LTRIM(RTRIM(CP.Telefono)) <> '' AND LTRIM(RTRIM(CP.Telefono)) <> 'NO TIENE' THEN 1 ELSE 0 END) AS con_telefono_util
FROM CC_Clientes_Tabla C LEFT JOIN CC_ContactosxCliente CP ON CP.ID = C.ContactoPrincipal;

PRINT '';
PRINT '=== 49. EL CONTACTO PRINCIPAL APUNTA AL MISMO CodCli? ===';
SELECT COUNT(*) AS total,
       SUM(CASE WHEN CP.CodCli = C.CodCli THEN 1 ELSE 0 END) AS mismo_cliente,
       SUM(CASE WHEN CP.CodCli <> C.CodCli THEN 1 ELSE 0 END) AS otro_cliente
FROM CC_Clientes_Tabla C JOIN CC_ContactosxCliente CP ON CP.ID = C.ContactoPrincipal;
