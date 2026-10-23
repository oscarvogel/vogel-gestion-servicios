# Módulo Electrotecniref: catálogo de repuestos y precios desde Flexxus (Firebird 3050)

> Documento de trabajo. Es el cuerpo del issue
> [#114 — Módulo Electrotecniref: catálogo de repuestos y precios desde Flexxus (Firebird 3050)](https://github.com/oscarvogel/vogel-gestion-servicios/issues/114).
> Al final está el registro de la sesión (qué se hizo, qué falta, pendientes).

## Qué hay que hacer

Un módulo **solo para Electrotecniref** que lee el catálogo de repuestos y sus precios desde el ERP
**Flexxus** (Firebird, puerto 3050) y los deja disponibles al operador cuando carga los repuestos de
una OT o arma un presupuesto.

La idea y el patrón salen de `dashboard_suevos` (repo privado `oscarvogel/dashboard_suevos`), que ya
consulta esas bases desde Python con `firebirdsql`.

## Por qué

Hoy en el sistema el repuesto es texto libre:

- `work_order_parts` guarda `description`, `item_code`, `unit_cost` y `unit_price` que vienen del
  legacy (CiberBrain), no de un catálogo.
- El editor "Trabajo realizado y repuestos utilizados" (`frontend/src/views/WorkOrdersView.vue`) pide
  la descripción a mano.
- El modal de presupuesto (mismo archivo, `quoteItems`) también: descripción, costo interno y precio
  al cliente tipeados.
- El precio de venta sale de `unit_cost` + markup (`pricing.parts_markup_percent`), sobre un costo que
  alguien carga a mano.

El catálogo y los precios reales están en Flexxus: `ARTICULOS` (9697 filas en `DB-ETR.gdb`) con
`STOCK`, `RUBROS`, `MARCAS` y `MONEDAS`. Leerlos evita que el operador invente precios y deja el
precio trazable a un dato real, que es lo que ya exige #92.

## Cómo se conecta

- **Firebird remoto, puerto 3050.** No hay base local: la app abre TCP contra el servidor Firebird.
  La "base" es la ruta del `.gdb` **vista desde el servidor** (p. ej.
  `C:\FLEXXUS\DB\ETR\DB-ETR.gdb`), no del contenedor.
- Driver: `firebirdsql` (cliente puro Python, no requiere `fbclient`; ya corre en Docker en
  `dashboard_suevos`).
- Charset: `ISO8859_1`, el que funciona contra esas bases.
- Variables de entorno (plataforma, no por tenant): `FLEXXUS_HOST`, `FLEXXUS_PORT` (3050),
  `FLEXXUS_USER`, `FLEXXUS_PASSWORD`, `FLEXXUS_CHARSET`, `FLEXXUS_DATABASE`.
- La contraseña **no** va en el repo ni en la base: va en variable de entorno / secret del deploy.

## Solo Electrotecniref

El módulo se habilita únicamente para la empresa con slug `electrotecniref` (Electrotecniref, id=7),
que es el tenant que compra repuestos en Flexxus. Para cualquier otra empresa el endpoint responde
"no disponible" sin abrir conexión.

Se propone un parámetro de empresa nuevo (`flexxus.enabled`, `flexxus.database`) para que la
habilitación sea explícita y reversible, en lugar de clavar el slug en el código.

## Diseño propuesto

1. **Adaptador nuevo** `backend/app/integrations/flexxus/` (al lado de `whatsapp/`), siguiendo lo que
   dice el README: "adaptadores separados". Ahí va la conexión y las consultas; el dominio no importa
   nada de Firebird.
2. **Cliente read-only defensivo**: helpers `_table_exists` / `_column_exists` como los del dashboard.
   Si la tabla o la columna no existe en esa base, la consulta devuelve vacío en vez de reventar.
3. **Servicio** `backend/app/services/spare_parts.py` con `buscar_repuestos(query, limit)` y
   `obtener_repuesto(codigo)`, que devuelve: código, descripción, rubro, marca, stock actual, stock
   mínimo, costo, moneda y precio de venta.
4. **Endpoint** `GET /api/v1/spare-parts/search?q=<texto>&limit=<n>` con
   `require_permission("work_orders.view")` y tenant de `get_current_company_id` (nunca un
   `company_id` libre del frontend).
5. **UI**: el input de texto de "Repuesto" (ejecución) y el del modal de presupuesto pasan a combo con
   **autocomplete** contra ese endpoint. El texto elegido tiene que coincidir con una opción: si no
   coincide, no se guarda y se frena el envío.
6. **Trazabilidad**: la línea guarda el código del artículo y el origen del precio (`item_code` en
   `work_order_quote_items` / `work_order_execution_items`, más `price_source` y `price_synced_at` si
   se quiere saber cuándo se leyó).
7. **Dependencia**: `firebirdsql` como extra en `backend/pyproject.toml` (igual que el extra `import`
   de `pymssql`), para que el deploy normal no lo exija y la CI no dependa del ERP.

## El spike previo (bloqueante para los precios)

En el dashboard actual **no hay ninguna consulta de precio de venta**: se usa
`ARTICULOS.PRECIOCOMPRA` (costo) y `MONEDAS.CAMBIO` (cotización). Dónde vive el precio de venta
(columna en `ARTICULOS` o tabla de listas) **no está verificado contra el esquema real**.

Antes de escribir el servicio hay que correr un probe read-only contra el 3050 que:

1. liste tablas cuyo nombre contenga `PRECIO` / `LISTA` / `TARIFA` y sus columnas;
2. liste las columnas de `ARTICULOS` con nombre de precio;
3. devuelva 3 filas de ejemplo de cada candidata.

El probe se deja como `backend/scripts/probe_flexxus_esquema.py` (patrón `tools/probe_*.py` del
dashboard) y su salida en `docs/spike-esquema-flexxus.md`. Sin ese resultado, la parte de precio del
issue queda bloqueada: **no se implementa a ciegas**.

## La restricción que no se negocia

- **Flexxus es solo lectura.** Solo `SELECT`. Nunca `INSERT` / `UPDATE` / `DELETE`, nunca se toca el
  ERP.
- **No se inventan precios.** Si el precio no viene de Flexxus, la línea queda sin precio y el
  presupuesto lo marca pendiente (igual que #92). No se estima en silencio.
- **No se copia el catálogo a MySQL** en este issue. La lectura es contra el ERP. (Si después hace
  falta performance offline, es otro issue.)
- **Si Flexxus no responde** (timeout, 3050 caído, base caída): la búsqueda degrada a vacío con un
  aviso y la OT sigue operando. La app no se cae.
- **Credenciales fuera del repo y fuera de la base.** En la base, solo el dato no sensible de qué base
  usa la empresa.
- **Tenant**: todo lo que devuelve el endpoint es de la empresa activa.

## Criterios de aceptación

- [ ] El cliente Firebird conecta contra el servidor por 3050 con las credenciales de entorno; la
      contraseña no aparece en el repo ni en los logs.
- [ ] El probe del esquema está hecho y su salida está en `docs/spike-esquema-flexxus.md`, con la
      columna o tabla de **precio de venta** confirmada.
- [ ] `GET /api/v1/spare-parts/search?q=ABC` devuelve artículos de `ARTICULOS` (código, descripción,
      rubro, stock, stock mínimo, costo, moneda, precio de venta), filtrando por código o descripción
      (contiene, ignora mayúsculas y acentos) y con límite.
- [ ] Para una empresa que no es Electrotecniref el endpoint responde "no disponible" sin abrir
      conexión.
- [ ] Si la tabla o la columna no existe en la base, la consulta devuelve vacío sin excepción.
- [ ] Si el ERP no responde, la búsqueda degrada sin romper la carga de la OT ni la generación del
      presupuesto.
- [ ] El combo de repuestos (ejecución y presupuesto) es autocomplete contra ese endpoint, no texto
      libre; lo que no coincide con una opción no se guarda.
- [ ] La línea guardada conserva el código del artículo y el origen del precio, y el presupuesto
      muestra el mismo precio que el ERP.
- [ ] Tests: cliente (tabla/columna inexistente → vacío; ERP caído → degradado), API (tenant,
      permiso, límite) y una corrida contra la base real documentada.
- [ ] `firebirdsql` quedó como extra en `backend/pyproject.toml`; la CI corre sin el ERP.

## Fuera de alcance

- Escribir en Flexxus (pedidos, OTs, movimientos de stock, sincronización de stock).
- Sincronizar el catálogo completo a MySQL.
- Dashboard comercial: eso ya lo resuelve `dashboard_suevos`.
- Herramienta de IA `agregar_repuesto` que busque en catálogo: queda para un issue aparte, sobre este.

## Referencias

- `dashboard_suevos` (privado): `dashboard_app/firebird_repo.py` (consultas),
  `dashboard_app/config.py` (config y variables), `docs/conexion_firebird_etr.md` (conexión probada
  por 3050 el 2026-06-01), `scripts/probe_brand_stock_valuation.py` (patrón de probe).
- #92 — Presupuestos con IA desde datos reales (de dónde sale la exigencia de que el precio sea
  trazable a un dato real).
- `docs/arquitectura.md` — multiempresa y fechas.

## Dudas abiertas (para resolver antes de implementar)

- ¿El precio de venta en Flexxus es una columna de `ARTICULOS` o vive en una tabla de listas? Sin
  el probe no se puede cerrar el diseño de la respuesta.
- ¿El rubro de Flexxus se usa para filtrar por marca? Ojo: en vogel-gestion las marcas son la
  dimensión `work_areas` (los clientes de Electrotecniref), y el rubro del ERP del proveedor no es la
  misma dimensión. Hay que decidir si el rubro se usa como dato de referencia o como filtro.
- ¿La base que corresponde a Electrotecniref es `DB-ETR.gdb` o `DB-MLT-ETR.gdb`? El dashboard
  consulta las dos y `DB-MLT-ETR.gdb` parece más transaccional/contable (sin maestros de artículos).

---

## Registro de la sesión (2026-10-22)

### Qué se hizo

- Se relevó el repo de referencia `oscarvogel/dashboard_suevos` (privado) para copiar el patrón de
  conexión: Firebird por TCP 3050 con `firebirdsql`, charset `ISO8859_1`, base como ruta del `.gdb`
  vista desde el servidor.
- Se verificó contra ese repo qué es lo que hoy se consulta de Flexxus: `ARTICULOS` (`codigoarticulo`,
  `descripcion`, `codigorubro`, `codigomarca`, `preciocompra`, `codigomoneda`), `STOCK` (`stockactual`,
  `stockminimo`), `RUBROS`, `MARCAS` y `MONEDAS` (`cambio`). `ARTICULOS` y `STOCK` tienen 9697 filas
  cada una en `DB-ETR.gdb` (conexión probada el 2026-06-01).
- Se revisó cómo el sistema actual maneja repuestos y precios: `work_order_parts` (del legacy
  CiberBrain) y los inputs de texto libre en `frontend/src/views/WorkOrdersView.vue` (ejecución y
  modal de presupuesto). El precio sale de `unit_cost` + markup `pricing.parts_markup_percent`.
- Se armó el issue #114 con el alcance, el diseño propuesto, la restricción de solo lectura, el spike
  previo y los criterios de aceptación.

### Qué se encontró y cómo se resolvió

- **No hay base local de Flexxus**: la conexión es remota por 3050. La "base" es la ruta del `.gdb`
  vista desde el servidor, no del contenedor. Quedó escrito en el issue para que nadie busque un
  `.gdb` en el filesystem del deploy.
- **El precio de venta no está verificado.** En `dashboard_suevos` no hay ninguna consulta de precio
  de venta: solo `ARTICULOS.PRECIOCOMPRA` (costo) y `MONEDAS.CAMBIO` (cotización). Por eso el issue
  pone el probe de esquema como paso bloqueante, en vez de asumir una columna.
- **Las credenciales no van por empresa.** En este repo las credenciales de WhatsApp van cifradas
  por tenant con Fernet (`Company.whatsapp_api_key_encrypted`), pero Flexxus es un ERP de plataforma
  con una sola base: la propuesta es variable de entorno + un parámetro de empresa que dice qué base
  usa, y el slug `electrotecniref` como habilitación explícita y reversible.
- **`firebirdsql` como extra en `pyproject.toml`**, igual que el extra `import` de `pymssql`: el
  deploy normal no lo exige y la CI no depende del ERP.

### Pendientes

- [ ] Correr el probe de esquema contra el 3050 y dejar el resultado en
      `docs/spike-esquema-flexxus.md` (bloqueante para la parte de precios).
- [ ] Confirmar con el usuario cuál base corresponde a Electrotecniref: `DB-ETR.gdb` o
      `DB-MLT-ETR.gdb`.
- [ ] Decidir si el rubro de Flexxus filtra por marca (`work_areas`) o queda como dato de referencia.
- [ ] Conseguir las credenciales del 3050 (`FLEXXUS_HOST`, `FLEXXUS_USER`, `FLEXXUS_PASSWORD`) para
      el entorno: van en secret del deploy, nunca en el repo.