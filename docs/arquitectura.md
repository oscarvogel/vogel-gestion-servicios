# Arquitectura

Multiempresa desde la primera migración. Toda entidad de negocio llevará `company_id` salvo tablas globales explícitas. La empresa activa se valida contra sesión y membresías; nunca se confía en un `company_id` libre enviado por frontend.

PortalVogel y WhatsApp se mantienen detrás de adaptadores.

## Fechas

Las fechas del flujo se guardan como **datetime naive en UTC**. El frontend las formatea
con `Company.timezone`; el backend nunca las interpola en hora de servidor.

Consecuencia: todo corte por día natural (actividad del día, antigüedad, inicio de semana)
se calcula con la medianoche **local de la empresa** y recién ahí se convierte a UTC para
consultar. `tzdata` es dependencia del backend a propósito: sin ella, en Windows,
`ZoneInfo` falla y cualquier empresa cae al fallback de huso en silencio.
