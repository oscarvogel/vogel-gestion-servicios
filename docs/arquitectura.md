# Arquitectura

Multiempresa desde la primera migración. Toda entidad de negocio llevará `company_id` salvo tablas globales explícitas. La empresa activa se valida contra sesión y membresías; nunca se confía en un `company_id` libre enviado por frontend.

PortalVogel y WhatsApp se mantienen detrás de adaptadores.

Flexxus (el ERP de los repuestos) es el tercer adaptador, y también es de **solo lectura**.

## Fechas

Las fechas del flujo se guardan como **datetime naive en UTC**. El frontend las formatea
con `Company.timezone`; el backend nunca las interpola en hora de servidor.

Consecuencia: todo corte por día natural (actividad del día, antigüedad, inicio de semana)
se calcula con la medianoche **local de la empresa** y recién ahí se convierte a UTC para
consultar. `tzdata` es dependencia del backend a propósito: sin ella, en Windows,
`ZoneInfo` falla y cualquier empresa cae al fallback de huso en silencio.

## Adaptador Flexxus (catálogo de repuestos)

El ERP Flexxus (Firebird) es de otro cliente y se consulta **en vivo**, en **solo lectura**.
El catálogo **no se copia** a MySQL: no hay tabla de repuestos espejo ni job de
sincronización. Lo que queda en nuestra base es la **trazabilidad** de lo que se usó
(`item_code`, `price_source`, `price_synced_at`).

Reglas que no se negocian:

- **Solo lectura.** La conexión se abre con `readonly=True` y todas las consultas son
  `SELECT`. Nunca se escribe en el ERP.
- **El precio se lee, no se calcula.** Viene de `PRECIOVENTA1` (o del `PRECIOCOMPRA` para el
  costo interno), con el margen que el ERP ya aplicó. Si el ERP no tiene el precio, la línea
  queda sin precio: no se estima en silencio.
- **Aguanta una base que no sea la esperada.** El ERP tiene 671 tablas y cambia entre
  versiones: si una tabla o una columna no está, la consulta devuelve vacío en vez de
  reventar.
- **Si el ERP no responde, se degrada.** La búsqueda vuelve vacía con aviso y la OT sigue
  funcionando: cargar una orden no puede depender de que el ERP esté de pie.
- **Aislamiento por tenant.** Solo la empresa que tiene el módulo prendido ve el catálogo.
  Para el resto, la respuesta es "no disponible" sin abrir conexión.

Dónde está:

| Pieza | Ruta |
|---|---|
| Adaptador (lo único que sabe de Firebird) | `backend/app/integrations/flexxus/client.py` |
| Servicio (gate por empresa, caché, precio) | `backend/app/services/spare_parts.py` |
| Endpoints | `backend/app/api/v1/spare_parts.py` |
| Habilitación por plataforma | `PUT /api/v1/companies/{id}/flexxus` (superadmin) |
| Combo de la UI | `frontend/src/components/SparePartPicker.vue` |
| Plan funcional | `docs/plan-repuestos-flexxus.md` |
| Bitácora del deploy | `docs/sesion-2026-10-24-deploy-flexxus.md` |
