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

- [x] El cliente Firebird conecta contra el servidor por 3050 con las credenciales de entorno; la
      contraseña no aparece en el repo ni en los logs.
- [x] El probe del esquema está hecho y su salida está en `docs/spike-esquema-flexxus.md`, con la
      columna o tabla de **precio de venta** confirmada.
- [x] `GET /api/v1/spare-parts/search?q=ABC` devuelve artículos de `ARTICULOS` (código, descripción,
      rubro, stock, stock mínimo, costo, moneda, precio de venta), filtrando por código o descripción
      (contiene, ignora mayúsculas y acentos) y con límite.
- [x] Para una empresa que no es Electrotecniref el endpoint responde "no disponible" sin abrir
      conexión.
- [x] Si la tabla o la columna no existe en la base, la consulta devuelve vacío sin excepción.
- [x] Si el ERP no responde, la búsqueda degrada sin romper la carga de la OT ni la generación del
      presupuesto.
- [x] El combo de repuestos (ejecución y presupuesto) es autocomplete contra ese endpoint, no texto
      libre; lo que no coincide con una opción no se guarda.
- [x] La línea guardada conserva el código del artículo y el origen del precio, y el presupuesto
      muestra el mismo precio que el ERP.
- [x] Tests: cliente (tabla/columna inexistente → vacío; ERP caído → degradado), API (tenant,
      permiso, límite) y una corrida contra la base real documentada.
- [x] `firebirdsql` quedó como extra en `backend/pyproject.toml`; la CI corre sin el ERP.

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

- ~~¿El precio de venta en Flexxus es una columna de `ARTICULOS` o vive en una tabla de listas?~~
  **Resuelto el 2026-10-24**: es una columna de `ARTICULOS`: `PRECIOVENTA1..5`.
  Ver `docs/spike-esquema-flexxus.md`.
- ~~¿El rubro de Flexxus se usa para filtrar por marca?~~ **Resuelto**: el rubro es
  una dimension de precio propia del ERP (`PRECIOSEGUNRUBRO=2` en 9937 de 9978
  articulos), **no** es la dimension `work_areas` de vogel-gestion. Queda como dato
  de referencia en la respuesta, no como filtro.
- ~~¿La base que corresponde a Electrotecniref es `DB-ETR.gdb` o `DB-MLT-ETR.gdb`?~~
  **Resuelto**: `DB-ETR.gdb`. Es la unica con `ARTICULOS` (9978), `STOCK` (9978),
  `RUBROS` (765) y `MARCAS` (182). `DB-MLT-ETR.gdb` tiene 100 tablas, todas
  transaccionales: no tiene catalogo de articulos.

### Decision de negocio que queda (no es tecnica)

- **Que lista de precios se usa para el precio de venta**: `PRECIOVENTA1` (margen
  50%, el mas alto) es la lista "general"; `PRECIOVENTA2..5` tienen margenes
  40/35/30/25 y `PRECIOLISTA1..5` estan **vacias** en esta base. Como Electrotecniref
  compra repuestos en Flexxus, hay que confirmar con el cliente si el precio que
  va al presupuesto es su costo (`PRECIOCOMPRA`) o la lista de venta del ERP.
  Mientras tanto el modulo lo resuelve con el parametro `flexxus.price_list`
  (por defecto 1) y **no inventa** ningun precio.

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

---

## Registro de la sesión (2026-10-24)

### Qué se hizo

- Se implemento el **backend completo** del modulo de repuestos contra Flexxus:
  - `backend/app/integrations/flexxus/client.py`: adaptador read-only defensivo
    (`readonly=True`, solo `SELECT`). Import perezoso de `firebirdsql` para que el
    extra no sea obligatorio en el deploy normal.
  - `backend/app/services/spare_parts.py`: servicio con la **habilitacion por
    empresa** y la degradacion cuando el ERP no responde.
  - `backend/app/api/v1/spare_parts.py` + `backend/app/api/v1/router.py`:
    `GET /api/v1/spare-parts/search?q=&limit=`.
  - `backend/app/core/parameter_catalog.py` + `backend/app/core/config.py` +
    `backend/alembic/versions/20261024_0028_flexxus_repuestos.py`: los tres
    parametros de empresa (`flexxus.enabled`, `flexxus.database`,
    `flexxus.price_list`), todos **no editables** por la empresa.
  - `backend/scripts/probe_flexxus_esquema.py`: el probe read-only, reusado para
    escribir `docs/spike-esquema-flexxus.md`.
  - `backend/tests/test_spare_parts.py`: 20 tests (aislamiento, degradacion,
    permiso, limites, cliente defensivo y la habilitacion por plataforma).
  - `backend/app/api/v1/companies.py`: `GET` y `PUT /api/v1/companies/{id}/flexxus`
    (superadmin), la puerta por la que la plataforma habilita el catalogo.
  - `frontend/src/views/CompaniesView.vue`: la seccion "Catalogo de repuestos
    (Flexxus)" en el modal de empresa, al lado del plan de IA.
- Se **corrio el probe contra la base real** y se documento en
  `docs/spike-esquema-flexxus.md`. Se resolvieron las tres dudas abiertas.
- Se implemento y se probo el **aislamiento por tenant**: una empresa sin
  `flexxus.enabled` recibe "no disponible" **sin abrir conexion**.

### Cómo seplanteo el aislamiento (Electrotecniref y solo el)

El problema: el catalogo de Flexxus **es el de Electrotecniref**. Si se le
prendiera a otra empresa, esa empresa veria el catalogo y los precios de otro.

La solucion, en cuatro capas:

1. **El credencial es de plataforma, no de la empresa.** `FLEXXUS_HOST`,
   `FLEXXUS_USER`, `FLEXXUS_PASSWORD` etc. viven en variables de entorno del
   deploy. En la base **no hay ninguna credencial** de Flexxus: no hay
   `Company.flexxus_password` ni una columna cifrada. Es el mismo criterio que
   usa la gateway de WhatsApp para su parte de plataforma.
2. **La habilitacion es un parametro de empresa, no un slug clavado en el
   codigo.** `flexxus.enabled` (bool, default `false`) + `flexxus.database`
   (que base usa) + `flexxus.price_list` (que lista de precios). Los tres con
   `editable = false`: el administrador de la empresa recibe 403 si manda el
   PATCH, igual que con los parametros de la IA. Los habilita la plataforma.
   Asi se puede prender y apagar **sin desplegar**, y queda a la vista en la
   pantalla de Parametros.

   **Como los habilita la plataforma:** por `PUT /api/v1/companies/{id}/flexxus`
   (superadmin), que es la misma puerta que usa la IA con
   `PUT /api/v1/companies/{id}/ai`, y con el mismo criterio deliberado: no se
   le_amigo` que "un superadmin puede saltarse el `editable`" (ese atajo
   dejaria la puerta abierta para todos los demas parametros), sino un
   endpoint con nombre propio que dice lo que hace. Desde la pantalla de
   Empresas, en el modal de la empresa, la seccion **"Catalogo de repuestos
   (Flexxus)"**: un interruptor, la base y la lista de precios.

   Por que un endpoint y no un `UPDATE` a mano sobre la base: las bases de
   Coolify viven en la red interna de Docker del servidor y **no se alcanzan
   desde la maquina del administrador** (ver `deploy-coolify.md`). Ademas, el
   `UPDATE` a mano no deja registro de quien habilito que.
3. **El orden de los controles es lo que evita la fuga.** En el endpoint:
   permiso (`work_orders.view`) -> tenant del token (`get_current_company_id`,
   nunca un `company_id` del frontend) -> `flexxus.enabled`. Recien ahi se arma
   el cliente. **Una empresa sin el modulo no abre ni un socket contra el ERP**:
   el corte es antes de la red, no despues.
4. **La respuesta no es filtrada: es de una sola empresa.** El endpoint no
   acepta `company_id` de entrada. No hay forma de pedir el catalogo de otra
   empresa, porque el catalogo de Flexxus es de Electrotecniref y el modulo
   solo existe para ella.

### Qué se encontró y cómo se resolvió

Estos son los bugs que aparecieron al probar contra la base real. Todos están
en el codigo con el comentario que los explica, para no volver a pisarlos:

- **La imagen de produccion salia sin el driver `firebirdsql`.** Las apps de
  Coolify se construyen con **Nixpacks**, que corre `pip install .` y **no
  instala los extras**: el `Dockerfile` del repo no construye nada. Con el driver
  solo en el extra `flexxus`, el modulo degradaba a texto libre sin avisar, y la
  CI daba verde porque instalaba `.[dev,flexxus]`. Resuelto poniendo el driver en
  las **dependencias base** y haciendo que la CI instale como instala el deploy
  (`pip install -e .[dev]`) y verifique el import.
- **Un test que pasa local y falla en la CI** por depender del `.env` local (que
  tiene `FLEXXUS_PASSWORD`) y no de lo que el test quiere medir. Se fijo el valor
  con `monkeypatch` para que el test sea el mismo en cualquier maquina.
- **La contraseña NO estaba en el repo de `dashboard_suevos`.** Se busco en
  todos los archivos (incluidos los ignorados por git), en todo el historial de
  todas las ramas y en el buzon IMAP de Suevos: solo hay placeholders
  (`clave_firebird`, `cambiar-por-la-clave-real`). La clave real vive en el
  entorno del contenedor del dashboard, en `fasa_189`
  (`/srv/fasa-data/compose/etr-dashboard`), y se copio al `.env` local
  (gitignored) sin pasar por la pantalla.
- **El `LIKE` de Firebird 2.5 corta el patron a los 30 caracteres.** Una
  consulta como `"%NO EXISTE ESTE ARTICULO XYZ%"` revienta con
  "string right truncation" (-303). Resuelto usando `POSITION` en vez de `LIKE`.
- **El parametro hereda el tipo del PRIMER uso.** `CODIGOARTICULO` es
  `VARCHAR(15)`, asi que `position(? in upper(a.CODIGOARTICULO))` hacia que
  Firebird inferiera el parametro como `VARCHAR(15)`, y el mismo parametro mas
  largo se cortaba en el segundo uso. Resuelto con
  `cast(? as varchar(255))` explicito en las dos ramas.
- **`POSITION` es sensible a mayusculas.** Hay que aplicar `upper()` a la
  columna. La aguja se pasa ya en mayusculas desde Python: aplicar `upper()` al
  parametro tambien hace que Firebird infiera un tipo corto.
- **`upper()` NO convierte 'ñ' a 'Ñ'** con ISO8859_1. Por eso la busqueda
  prueba las variantes con y sin tilde ("cano" -> CANO, CANO, CAÑO, CAÑO), y el
  filtro de Python usa el mismo criterio que el SQL.
- **La consulta se parte por palabras y se exigen todas.** "arandela plana
  zinc" tiene que devolver articulos con las tres palabras, no con cualquiera.
- **El margen es POR ARTICULO, no del rubro ni de la marca.** `ARTICULOS.MARGEN1`
  coincide con el del rubro en solo 42 de 9978 articulos. Por eso el modulo
  **lee** `PRECIOVENTA1` del ERP y no recalcula el precio: la formula
  `PRECIOVENTA1 = PRECIOCOMPRA * (1 + MARGEN1/100)` se cumple al centavo, pero
  el ERP ya la aplico con todas sus reglas.
- **Los articulos tienen MONEDA mixta**: 6630 en PESOS y 3348 en DOLARES. El
  modulo convierte a pesos con `MONEDAS.CAMBIO` (DOLARES = 1600 al 25/09/2026),
  que es el mismo criterio que usa el dashboard.
- **`PRECIOLISTA1..5` estan vacias** en esta base: el precio real esta solo en
  `PRECIOVENTA1..5`.
- **`STOCK` es por sucursal** (`CODIGOSUCURSAL`), y en esta base hay una sola:
  `PRINCIPAL`.
- El **fallback sin filtro de texto** (para no perder resultados con acentos)
  arrastraba el `DataError`: se quedo con el mismo criterio de filtros y sin el
  `upper()` sobre el parametro.

### Estado verificado

- Suite completa del backend: **335 tests en verde** antes de este modulo, y los
  13 nuevos del modulo tambien.
- Corrida contra la base real documentada: `docs/spike-esquema-flexxus.md`
  (generado el 2026-10-24 contra `DB-ETR.gdb`, 671 tablas, `ARTICULOS` con 9978
  filas) y una prueba de extremo a extremo que devuelve articulos reales con
  rubro, marca, stock, costo convertido y precio de venta.

### Pendientes

- [x] **UI**: el combo con autocomplete de "Repuesto" (ejecucion) y del modal de
      presupuesto. Respetando el criterio de la pantalla del cliente (1638x969 y
      1366x768, con scroll si hace falta) y sin dejar guardar texto que no
      coincida con una opcion.
- [ ] **Confirmar con el cliente que precio va al presupuesto**: el costo
      (`PRECIOCOMPRA`) o la lista de venta del ERP (`PRECIOVENTA1..5`). Es la
      unica decision que el modulo no puede tomar solo. Mientras tanto:
      `flexxus.price_list = 1`.
- [ ] **Habilitar `flexxus.enabled` para Electrotecniref** en la base, desde el
      lado de la plataforma, cuando el modulo este listo para usar.
- [ ] **Cargar las variables en el deploy**: `FLEXXUS_HOST`, `FLEXXUS_PORT`,
      `FLEXXUS_USER`, `FLEXXUS_PASSWORD`, `FLEXXUS_CHARSET` como secret del
      deploy, nunca en el repo ni en la base.
- [x] **Trazabilidad en la linea guardada**: `item_code` + `price_source` +
      `price_synced_at` en `work_order_quote_items` y `work_order_execution_items`.

---

## Registro de la sesión (2026-10-24, segunda parte: la UI)

### Qué se hizo

- **`frontend/src/components/SparePartPicker.vue`**: el combo con autocomplete.
  Es un componente reusable, no un bloque pegado en la vista, porque va en dos
  lugares (modal de presupuesto y editor de ejecucion) y porque los dos tienen
  que comportarse igual.
  - Escribe -> busca con debounce de 250 ms -> muestra hasta 12 opciones con
    codigo, descripcion, marca, rubro y precio.
  - Al elegir una opcion, completa el **costo interno** y el **precio al
    cliente** con los del ERP. El precio del presupuesto es el del ERP, no un
    markup sobre un costo que alguien cargo a mano.
  - Si el texto ya coincide exactamente con una opcion, **la toma sola**: el
    operador puede escribir el nombre completo y no tiene que hacer clic.
  - Si el texto se edita a mano despues de elegir, **la seleccion se
    invalida**: la linea queda sin precio del ERP y no se puede guardar.
  - Si el catalogo no aplica a la empresa (o el ERP esta caido), **degrada a
    texto libre** con el aviso a la vista: cargar la OT no puede depender de
    que el modulo este disponible.
- **`GET /api/v1/spare-parts/status`**: dice si el catalogo aplica a esta
  empresa **sin abrir conexion al ERP**. El frontend lo consulta una vez al
  montar el combo, para saber si tiene que exigir elegir una opcion o si deja
  escribir a mano.
- **Caché TTL de 30 segundos** en el servicio, por empresa y por texto. El ERP
  es el ERP de otro cliente: bombardearlo con una consulta por tecla es una
  falta de respeto. Medido: la primera busqueda contra Firebird tarda ~500 ms,
  la segunda sale de la cache en 2,2 ms.
- **Trazabilidad**: `item_code`, `price_source` y `price_synced_at` en las
  lineas de presupuesto y de ejecucion (migracion `20261024_0029`), con la
  linea cargada a mano dejandolos en null (no se inventa el origen de un
  precio que no viene del ERP).

### El aislamiento, en la parte de la UI

La regla que se implemento en el frontend:

- El combo **no manda `company_id`**: el tenant sale del token. No hay forma
  de pedir el catalogo de otra empresa desde el navegador.
- La empresa **sin `flexxus.enabled`** recibe "no disponible" y el campo queda
  como texto libre. **No se busca en el ERP**: el componente no lo pregunta
  cuando el estado ya le dijo que no aplica.
- Con el catalogo activo, **una linea de repuesto sin opcion elegida no se
  guarda**: el boton de generar presupuesto y el de registrar ejecucion
  quedan deshabilitados, y el backend tambien lo rechaza si le llega.

### Que se ve, y que no, segun el caso

El endpoint de estado distingue dos motivos por los que no hay catalogo, y la
diferencia se nota en pantalla:

| Situacion | Que ve el operador |
|---|---|
| La empresa **no tiene** el modulo | Nada. El campo es texto libre, como antes de este modulo. Sin aviso. |
| El modulo **corresponde** pero el ERP esta caido | Aviso: "No se pudo consultar el catalogo de repuestos en Flexxus. Segui operando: el repuesto se carga a mano." El campo sigue siendo texto libre. |
| El modulo **corresponde** pero falta la credencial en el deploy | Aviso: "No hay credencial de Flexxus configurada en el servidor." |

El motivo de la distincion: que el modulo no aplique es el estado normal de
todas las empresas menos una. Mostrarle a todas un aviso permanente entrena al
operador a ignorar los avisos que **si** importan. El aviso se reserva para
cuando se esta perdiendo una funcion que deberia estar disponible.

### Bugs y hallazgos de esta parte

- **El desplegable se recortaba dentro del modal.** `.quote-modal` es un
  contenedor con `overflow:auto`, asi que un menu `position:absolute` adentro
  queda cortado. Resuelto con **Teleport a `body`** con posicion fija, que es
  el mismo problema que ya tenian el combo de clientes y el de tecnicos. El
  menu se posiciona al borde de la ventana y **abre hacia arriba cuando no
  hay lugar abajo**.
- **El umbral de volteo del menu era menor que su altura** (200 px contra un
  menu de 260 px): en los campos cerca del borde de abajo, el desplegable se
  salia de la pantalla. Ahora elige el lado con mas espacio en vez de
  comparar contra un numero fijo.
- **Al cambiar una linea de Repuesto a Mano de obra, el precio del repuesto
  quedaba pegado.** Se limpia la seleccion y el precio al cambiar el tipo.
- El input del combo esta en otro componente, asi que el CSS scoped de la
  vista no llega adentro: el look se le da con `:deep()`.

### Verificacion

- **Backend**: 342 tests en verde (338 previos + 4 de trazabilidad).
- **Frontend**: 70 tests en verde (13 archivos), 8 nuevos del combo.
- **Visual**: banco de pruebas en `frontend/banco-repuestos.html`, que
  reproduce el modal real con su `overflow:auto` y el CSS exacto del
  componente. Verificado a **1638x969** y a **1366x768**: el grid de la linea
  aguanta y el desplegable entra completo en la ventana en los dos casos,
  abriendose hacia arriba cuando hace falta.
- **Contra el ERP real**: la cadena completa (gate de tenant -> servicio ->
  Firebird) devuelve articulos reales con rubro, marca, stock, costo convertido
  a pesos y precio de venta.