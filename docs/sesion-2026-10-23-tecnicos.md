# Sesión 2026-10-23 — Maestro de técnicos y asignación de técnicos a la orden

Objetivo de la sesión: que se pueda **cargar a los técnicos** y **asignar uno a una orden de
trabajo**, incluida la OT que se crea en recepción. El legacy (CiberBrain) no tenía maestro de
técnicos: el importador lo derivó de los intervinientes.

**Estado al terminar:**

- Maestro de técnicos completo: API + pantalla, con permisos `technicians.view` / `technicians.manage`.
- Asignación y retiro de técnicos desde el detalle de la OT y desde la recepción.
- Backend **322 tests en verde**, frontend **48 tests en verde**.
- La migración `20261023_0027` (permisos) queda aplicada en la base local; en staging corre sola
  en el próximo deploy (el contenedor hace `alembic upgrade head`).

---

## 1. Qué se entregó

### Backend

| Qué | Dónde | Nota |
|---|---|---|
| Permisos `technicians.view` / `technicians.manage` | `backend/app/core/permissions.py` | |
| Migración de permisos | `backend/alembic/versions/20261023_0027_permisos_tecnicos.py` | patrón de la 0025; concede a "Administrador" |
| Dependencia `require_any_permission(*codes)` | `backend/app/api/dependencies.py` | alcanza con uno de varios permisos |
| API del maestro | `backend/app/api/v1/technicians.py` | `GET/POST /technicians`, `PATCH /technicians/{id}` |
| Asignación en la OT | `backend/app/api/v1/work_orders.py` | `GET/POST /{id}/technicians`, `DELETE /{id}/technicians/{tid}` |
| Técnico en la recepción | `backend/app/services/work_orders.py` | `crear_orden(..., technician_id=...)` |
| Tests | `backend/tests/test_technicians.py` | 6 tests |

El listado del maestro acepta `technicians.view` **o** `work_orders.manage`: quien arma la orden
tiene que poder elegir a alguien aunque no administre el maestro. La asignación, en cambio, es
parte de **gestionar la orden** (`work_orders.manage`).

### Frontend

| Qué | Dónde |
|---|---|
| Pantalla del maestro | `frontend/src/views/TecnicosView.vue` (+ `IconTecnicos.vue`) |
| Ruta y link | `frontend/src/router.ts`, `frontend/src/components/Sidebar.vue` |
| Panel de técnicos en la OT | `frontend/src/views/WorkOrdersView.vue` |
| Combo de técnico en la recepción | `frontend/src/views/WorkOrdersView.vue` |
| Tests | `frontend/src/__tests__/tecnicos.test.ts` (11 tests) |

El combo filtra por "contiene", ignora mayúsculas y acentos, y **no deja guardar un nombre
suelto**: si el texto no coincide con nadie de la lista, no se guarda nada.

---

## 2. Decisiones

- **El maestro es por empresa** (`company_id`), como el resto de los maestros.
- **Desactivar no desasigna**: un técnico desactivado sigue figurando en las órdenes donde ya
  estaba (el histórico no se toca) pero ya no se puede asignar a ninguna más.
- **No se recalcula ninguna comisión** al asignar: el legacy traía el importe ya calculado y eso
  no se toca. Asignar sólo escribe el vínculo y el evento del historial.
- **En la recepción el técnico es opcional**: en el legacy el técnico se asignaba después, en el
  taller.

---

## 3. Bugs encontrados y cómo se diagnosticaron

### 3.1 `apiDelete` no estaba importado (serio, rompía la función)

`WorkOrdersView.vue` usaba `apiDelete(...)` en dos lugares —dar de baja un documento y **quitar
un técnico**— pero el import de `../lib/api` no lo incluía. La llamada lanzaba `TypeError` dentro
del `try`, el `catch` lo convertía en un toast de error y **la función no hacía nada**.

No lo detectaba el build: el script `build` es `vite build` **sin `vue-tsc`**, así que el
proyecto no type-chequea en ningún momento. El import faltante llegó hasta el commit.

**Arreglo:** agregar `apiDelete` al import. **Para evitar que vuelva:** agregar `vue-tsc --noEmit`
al `package.json` (hoy no hay `vue-tsc` en las devDependencies). Queda como pendiente (§5).

### 3.2 La pantalla de la OT entera se caía con una respuesta inesperada

Dos cargadores CONFÍABAN en la forma de la respuesta:

```ts
notifications.value = r.items                                   // si la respuesta no trae "items" -> undefined
orderDocuments.value = (await apiGet(...)).items               // idem
```

Con `undefined`, la plantilla hace `notifications.length` y **`RangeError`/`TypeError` en el
render**: no se actualiza ninguna parte de la pantalla. Como el render aborta, el resto de la
página se queda con el estado anterior y el error se ve como "la pantalla no hace nada".

**Arreglo:** ambos validas `Array.isArray(r?.items) ? r.items : []`.

### 3.3 `formatCompanyDate` reventaba con una fecha vacía

`new Intl.DateTimeFormat(...).format(new Date("undefinedZ"))` lanza `RangeError: Invalid time
value`. La fecha se usa en el diagnóstico (`diagnosis.updated_at || diagnosis.diagnosed_at`) y en
varios lugares más. `formatDocDate` ya lo manejaba ("—"); `formatCompanyDate` no.

**Arreglo:** si la fecha no es válida, se muestra "—" en vez de romper el render.

### 3.4 En los tests, el componente veía otra sesión (pinia 3)

Con `pinia@3.0.4`, `useStore()` **sin argumento** no usa siempre el pinia activo: si hay contexto
de app, hace `inject(piniaSymbol)` y puede devolver **otra instancia** del store. El test parcheaba
la sesión con `useSessionStore()` y el componente leía una copia distinta (sin permisos), por lo que
el panel de técnicos no se renderizaba y los tests fallaban "sin motivo".

**Arreglo:** pedir siempre el store con el pinia explícito —`useSessionStore(pinia)`— que es
exactamente la instancia que el componente va a usar. Aplicado en `tecnicos.test.ts` y en
`cierre-marcas.test.ts` (que tenía la misma fragilidad).

### 3.5 El filtro de técnicos: "alli" no matchea con "Alladio"

El técnico de la lista se llama **Alladio** (A-l-l-a-d-i-o). La subcadena "alli" **no** existe
dentro de "alladio": el filtro correcto es "allad" o "alladio". El componente estaba bien; el test
buscaba una subcadena que no estaba.

Vale la pena dejarlo anotado porque el nombre "Alladio" invita a escribir "alli" y el combo
legítimamente no encuentra a nadie.

---

## 4. Cómo verificar

```powershell
# Backend (base local MySQL en WSL, puerto 3307)
cd C:\Programacion\vogel-gestion\backend
$env:DATABASE_URL='mysql+pymysql://vogel:change_me@localhost:3307/vogel_gestion_servicios'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests -q --rootdir . -c pyproject.toml

# Frontend
cd C:\Programacion\vogel-gestion\frontend
npx vitest run
npm run build
```

En la pantalla: **Órdenes de trabajo → abrir una OT → "Técnicos asignados"** (agregar y quitar) y
**Órdenes de trabajo → + Nueva recepción → "Técnico (opcional)"** (el combo filtra y deja elegir
sólo a quien está en el maestro). El maestro está en **Técnicos**, en el menú lateral.

---

## 5. Los tres bugs que reportó el cliente (23/10/2026, tarde)

Después del despliegue, el cliente reportó tres cosas: que no podía elegir un técnico, que
desde el dashboard no podía abrir una nueva OT y que el listado mostraba "0 órdenes". Los tres
eran reales y ninguno era de backend.

### 5.1 El técnico de la recepción no se podía seleccionar (bug de CSS)

**Síntoma:** el desplegable del campo "Técnico (opcional)" se veía, pero el clic no surtía
efecto: no se podía elegir a nadie.

**Causa raíz:** el contenedor del combo es `<div class="field technician-picker">`, y la regla
que posiciona el desplegable es `.customer-picker{position:relative}`. La clase
`technician-picker` **no** estaba en esa regla, así que el `.customer-picker__menu`
(`position:absolute; top:100%; left:0; right:0`) se anclaba al ancestro posicionado más
cercano: el `.modal-backdrop`, que es `position:fixed` y ocupa toda la pantalla. El menú
aparecía en el borde inferior de la ventana, muy lejos del campo, y el usuario no lograba
hacer clic en él.

**Arreglo:** se agrega `.technician-picker{position:relative}` (y el `top:calc(100% + 4px)`
para pegarlo al campo, como hace `.technician-assign` en el detalle de la OT).

**Por qué no lo traduce el test:** jsdom no calcula posiciones, así que en el test el menú
"appears" donde debe. El test de regresión (`work-orders-deep-link.test.ts`) controla el
**fuente** del componente: si alguien saca la regla, el test falla.

### 5.2 "+ Nueva OT" del dashboard no abría el modal (dos causas)

El botón del dashboard es un `RouterLink` a `/app/work-orders?new=1`. La vista de órdenes
lee ese deep-link en `handleDeepLinks()`, pero:

1. **El `Promise.all` del `onMounted` se rechazaba.** Las cinco cargas iniciales iban en un
   `Promise.all` y `loadStatuses()` no tenía `try/catch`: si esa llamada fallaba (en staging
   pasó: un 500 transitorio mientras la base se reiniciaba y el backend no resolvía el
   nombre del contenedor de MySQL), el `Promise.all` rechazaba, el `onMounted` se cortaba y
   **`handleDeepLinks()` nunca se ejecutaba**: el modal no abría y el toast decía "Ocurrió un
   error interno".
2. **El watcher solo miraba `query.open`.** Si el usuario ya estaba en `/app/work-orders`,
   al cambiar la query la vista no se vuelve a montar (misma ruta, distinto query) y el
   watcher de `open` no se disparaba: el `?new=1` quedaba sin leer.

**Arreglo:** `Promise.allSettled` en el `onMounted` (que una carga falle no puede impedir el
deep-link), `try/catch` en `loadStatuses`, y el watcher pasa a mirar
`open, openId, id, new, action`. Además `newReception()` no vuelve a resetear el formulario si
el modal ya está abierto.

### 5.3 El listado mostraba "0 órdenes" (el token había perdido la empresa)

Lo primero que se hizo fue llamar a la API de staging **como el navegador**: login real
(`admin@electrotecniref.com.ar`), `POST /auth/select-company` con la empresa 3 y después
`GET /work-orders?page=1&page_size=25`. La respuesta fue **200 con `total: 9316` y 25
ítems**: el backend estaba bien.

Pero el navegador seguía mostrando "0 órdenes" con el bundle nuevo y una recarga. La
prueba que faltaba era mirar **qué código HTTP devolvía el navegador**, y no sólo el que
devolvía mi script. En el log de acceso de nginx del frontend:

```
GET /api/v1/work-orders?page=1&page_size=25   409
GET /api/v1/work-orders/statuses               409
GET /api/v1/technicians                        409
GET /api/v1/companies/current                  409
```

**409 "Active company required"**: el token que tenía el navegador **no traía `company_id`**.
O sea, no era que el listado viniera vacío: **todas** las consultas de empresa fallaban, y
`load()` se tragaba el error en un toast, así que la pantalla mostraba el estado vacío sin
explicar nada.

#### La causa raíz (de backend)

`create_refresh_token(user_id)` **no guardaba la empresa**:

- `/auth/login` devuelve un refresh token sin empresa (correcto: el usuario todavía no
  eligió empresa).
- `/auth/select-company` devolvía **solo** el access token: el refresh token guardado en el
  navegador seguía siendo el del login, sin empresa.
- `/auth/refresh` leía `company_id` del refresh token → siempre `None` → devolvía un access
  token **sin empresa**.

O sea: **cada vez que se renovaba el access token, el usuario volvía al modo plataforma** y
todas las consultas de empresa empezaban a dar 409. Como el token de acceso dura poco, el
problema aparecía "un rato después de loguearse" y se veía como si la pantalla se rompiera
sola.

**Arreglo (backend):**

- `create_refresh_token(user_id, company_id=None)` → el refresh token lleva la empresa.
- `/auth/select-company` devuelve además un **refresh token nuevo con la empresa**.
- `/auth/leave-company` devuelve un refresh token sin empresa (modo plataforma).

**Arreglo (frontend):**

- `selectCompany()`, `leaveCompany()` y el refresh de `api.ts` guardan el refresh token
  que devuelve el backend (antes solo guardaban el access token).
- `bootstrap()`: si la sesión se recarga **sin empresa guardada** y el usuario tiene **una
  sola** empresa activa, la elige solo. Antes la app entraba igual a las vistas de empresa
  con un token sin empresa y todo daba 409. Con varias empresas sigue yendo al selector.

#### Dos detalles que costaron tiempo y conviene no repetir

- **El token del login no trae `company_id`**: sin `POST /auth/select-company`, todo lo que
  sea de empresa responde **409 "Active company required"** (no 401). El login del frontend
  es el que resuelve ese paso.
- **El log de acceso de Coolify no muestra el cuerpo**, solo el estado. Para ver qué recibe
  el navegador hay que llamar a la API con el mismo token (`backup/_work/probe_staging.py`)
  **o leer el log de nginx del frontend**, que sí tiene el código HTTP de cada pedido.

Como defensa, `load()` valida la forma de la respuesta (`Array.isArray` sobre `items`,
`total` numérico) para que una respuesta inesperada muestre el estado vacío en vez de
romper el render, `loadStatuses()` tiene `try/catch` y el deep-link no depende de que las
cargas tengan éxito.

### 5.4 Cómo se diagnosticó (para no repetirlo)

| Paso | Qué se hizo | Qué apareció |
| --- | --- | --- |
| 1 | `GET /api/v1/work-orders` con login + `select-company` desde un script | **200 con 9.316** → el backend estaba bien |
| 2 | Log de nginx del frontend | **409 en todas** las consultas de empresa → el token no tenía empresa |
| 3 | `GET /api/v1/auth/me` del navegador | 200 con 1 membresía (empresa 3) |
| 4 | Botón "cambiar empresa" de la barra superior | **no estaba** → `activeCompany` era `null` → no había empresa guardada en el navegador |

El paso 4 es el que cierra el círculo: sin empresa guardada, `bootstrap()` no llamaba a
`select-company` y el token se quedaba en modo plataforma.

---
### 5.5 Dos ajustes mas sobre los tecnicos (a pedido del cliente)

**El input "Agregar un tecnico..." salia blanco.** En el detalle de la OT ese input no
vive dentro de un `.field`, asi que no heredaba la regla `.field input{background:
var(--color-surface); border: 1px solid var(--color-border); ...}` y se veia con el
default del navegador: un rectangulo blanco en medio de la pantalla oscura. Ahora
`.technician-assign input` lleva el mismo estilo (fondo, borde, radio, padding, color) y
el mismo estado de foco (`.technician-assign input:focus`) que el resto del sitio. El
input de la recepcion ya estaba bien: ese si esta dentro de un `.field`.

**Ver cuales tecnicos estan activos.** El maestro ya mostraba el estado de cada fila y el
contador ("44 activos de 44"), pero faltaba poder ver de un vistazo solo los activos, y
en la OT no se distinguishia un tecnico desactivado de uno activo. Ahora:

- El maestro tiene tres filtros con el mismo patron de chips de la pantalla de Empresas:
  **Todos / Activos (44) / Desactivados (0)**.
- Los chips de "Tecnicos asignados" en el detalle de la OT marcan **Inactivo** a los
  desactivados (chip apagado, no azul). Un tecnico desactivado sigue en las ordenes que
  ya tenia asignado (el historico no se toca), asi que hay que poder ver que ya no esta
  activo.
- Los selectores (recepcion y detalle de la OT) **solo ofrecen tecnicos activos**: el
  backend tambien lo rechaza con 409 ("El tecnico esta desactivado: activalo desde el
  maestro para poder asignarlo").
- El texto del selector de la recepcion ahora dice que solo se ofrecen los activos.

Test: `frontend/src/__tests__/tecnicos-activos.test.ts` (4 tests). Frontend: 60 tests en
verde.

---

### 5.6 Verificacion en el navegador (staging)

Con el backend y el frontend desplegados, se comprobo en el navegador (la pestana del
usuario, en la sesion real de staging):

| Que se verifico | Resultado |
| --- | --- |
| Listado de ordenes | "9316 ordenes en esta empresa" con la tabla llena |
| Combo de tecnicos de la recepcion | La lista (44 del maestro) abre **debajo del campo** y se puede elegir: "Alladio" quedo seleccionado con su boton "Quitar" |
| Filtro del combo | Escribir "allad" deja solo "Alladio" (filtra por contiene, ignora acentos) |
| "+ Nueva OT" del dashboard | La URL `/app/work-orders?new=1` abre el modal de "Nueva recepcion" y despues se limpia el query de la URL |
| Panel "Tecnicos asignados" del detalle de la OT | Aparece con el campo "Agregar un tecnico..." y la lista de disponibles |
| Sesion | La barra superior muestra la empresa (Electrotecniref) y el boton "Cambiar" |

La sesion del navegador se recuperó yendo a `/company-selector` y eligiendo la empresa:
el token que estaba en el navegador habia quedado en modo plataforma. Con el fix del
refresh token, eso ya no se repite, y `bootstrap()` vuelve a elegir sola la empresa si la
sesion se recarga sin ella guardada (cubierto por
`frontend/src/__tests__/sesion-empresa.test.ts`).

Puerto de la base: se cerro (`is_public=false`, `public_port=''`) al terminar el
diagnostico; la API de staging sigue respondiendo 200 con las 9.316 ordenes.

### 5.7 Como se subio a staging (y lo que costo)

La cola de deploys de Coolify es **compartida entre proyectos**: un deploy de otro
proyecto ("chat-central") estuvo `in_progress` un rato largo y dejo en cola los nuestros
(los deploys 1661/1662 del backend y el frontend). Durante la espera, el navegador
pide un asset que todavia no existe y el nginx responde **200 con el index.html** en
lugar del JS: la pagina queda en "Verificando tu sesion..." sin error visible. Si pasa
algo raro con la pagina en staging, primero mirar el estado de los deploys.

Cada deploy hay que pedirlo con el commit explicito:

```powershell
$body = @{ git_branch = 'feature/cyberbrain-migracion'; git_commit_sha = 'HEAD' } | ConvertTo-Json
Invoke-RestMethod -Uri "$api/api/v1/applications/<uuid>" -Headers $h -Method Patch -Body $body -ContentType 'application/json'
Invoke-RestMethod -Uri "$api/api/v1/deploy?uuid=<uuid>&force=true" -Headers $h -Method Post -ContentType 'application/json'
```

Y para saber si el bundle nuevo quedo servido hay que mirar el **nombre del asset** que
devuelve el `index.html` (`assets/index-<hash>.js`): si el hash no cambio, el deploy
todavia no termino o quedo en cola.

---

### 5.8 La causa de fondo del "0 ordenes": el proxy resolvia en IPv6

Despues de arreglar la sesion (5.3) el listado seguia mostrando "0 ordenes" en el
navegador, aunque la API llamada desde un script devolvia 200 con las 9.316 ordenes.
La diferencia era **el camino**: el script pegaba al backend por HTTPS, el navegador
pasa por el proxy nginx del frontend.

En el log de nginx del frontend:

```
[error] connect() failed (111: Connection refused) while connecting to upstream,
request: "GET /api/v1/work-orders?page=1&page_size=25",
upstream: "http://[fd04:36e8:6aaa::11]:8000/api/v1/work-orders?page=1&page_size=25"
```

**Causa:** el `resolver` de nginx (el DNS embebido de Docker, 127.0.0.11) devuelve
**las dos** direcciones del contenedor del backend: la A (IPv4) y la AAAA (IPv6). El
backend arranca con `uvicorn app.main:app --host 0.0.0.0 --port 8000`: escucha en IPv4
y **no** en IPv6. nginx elegia al azar entre las dos, y la mitad de las peticiones al
backend fallaban con "connection refused". La app recibia un 502, `load()` lo tragaba
en un toast y la pantalla quedaba en cero: "Todavia no hay ordenes de trabajo".

Por eso:
- desde un script (que pega al backend por HTTPS) siempre se veian 9.316 ordenes;
- en el navegador era intermitente, y a veces se veia la lista y a veces no;
- el `Promise.all` del `onMounted` (antes del fix) se caia con un solo fallo.

**Arreglo:** `frontend/nginx.conf` -> `resolver 127.0.0.11 valid=30s ipv6=off;` Con
`ipv6=off` nginx solo pide direcciones IPv4, que son las que el backend escucha.

**Como se comprueba:** `backup/_work/probar_proxy.py` pega 20 veces al backend a traves
del proxy (se espera 401 sin token). Antes del fix caia la mitad; ahora **20/20**.

Test de estructura: `frontend/src/__tests__/nginx-upstream.test.ts` (2 tests) deja
escrito que el resolver tiene que llevar `ipv6=off` y que el backend se resuelve por
nombre (una IP fija horneada en la imagen queda vieja en cada deploy).

### 5.9 Lecciones de este Diagnostico

1. **Probar por el mismo camino que el usuario.** Un script que pegue al backend no
   prueba el proxy: la mitad de los fallos vivian ahi.
2. **El codigo HTTP del navegador importa.** El log de acceso de nginx del frontend
   tiene el codigo de cada peticion; el de Coolify solo da estado, y el de la API no
   muestra ni el cuerpo.
3. **Un 502/499 en el log del proxy explica una pantalla vacia.** `499` es el cliente
   que corta la peticion; `connect() failed (111)` es el upstream que no acepta.
4. **Un test que pasa no siempre prueba el fix.** El test del proxy daba 20/20
   *con* el bug del IPv6, porque nginx reintenta la misma peticion contra otra
   direccion del AAAA y termina respondiendo igual. Lo que prueba el fix es el log:
   cero lineas con IPv6.

### 5.10 Subir todo a GitHub y desplegarlo en Coolify

**Qué se subió.** Primero las herramientas de la sesión, que hasta ahora vivían
sueltas en `backup/_work/` (commit `f4222b2`): los scripts de verificación
(`probar_proxy.py`, `verificar_sesion.py`, `probe_staging.py`, `repro_*.py`,
`ver_*.py`) y los de despliegue (`deploy_*.ps1`, `monitor_deploy*.ps1`,
`esperar_*.ps1`, `logs_*.ps1`, `ver_*.ps1`, `cerrar_puerto_base.ps1`).

Antes de commitearlos se limpiaron **credenciales**: los tres scripts que
tenían la contraseña de staging hardcodeada ahora la leen de
`STAGING_PASSWORD` / `STAGING_DATABASE_URL`, y el mail a Electrotecniref
lleva la contraseña reemplazada por la nota de que se envía aparte. Se
**quedaron fuera** el volcado de la app de Coolify (`front_app.json`, trae los
secretos de los webhooks) y los scripts de parcheo de un solo uso.

**El trabajo del otro worker ya estaba en `main`.** El working tree tenía
cambios sin commitear de "Consumo de IA" (`ai.py`, `companies.py`, `usage.py`,
`Sidebar.vue`, `router.ts`, `AiConsumoView.vue`, `test_ai_consumo.py`). Al
auditarlo:
- `ai.py`, `companies.py` y `usage.py` son **byte a byte iguales** a `main`.
- Los otros tres son iguales a `main` salvo el fin de línea (CRLF vs LF).
- Esos cambios entraron a `main` por el PR #112 (`483e84c`), que ya está
  mergeado, y la rama `feat/ia-consumo` ya no existe en el remoto.

O sea: **no había nada suyo pendiente de subir** y no se commiteó nada suyo.
Lo que sí se commiteó es el trabajo propio, que estaba en la rama.

**El merge a `main` (8 conflictos).** `main` ya traía el cierre a marcas
(#113) y mi rama traía el mismo trabajo con otra historia, así que los dos
lados tenían los mismos archivos, pero con commits distintos. Conflictos:

| Archivo | Cómo se resolvió |
|---|---|
| `frontend/src/router.ts` | **Unión**: `main` traía la ruta de Consumo de IA y la rama las de Cierre a marcas y Técnicos. Se quedaron las tres. |
| `frontend/src/components/Sidebar.vue` | Auto-merge, y se verificó que quedaron los tres links (`cierre-marcas`, `tecnicos`, `consumo-ia`). |
| `backend/app/core/permissions.py` | Versión de la rama: `main` + `technicians.view` / `technicians.manage`. |
| `backend/app/models/warranty_settlement.py`, `api/v1/warranty_settlements.py`, `services/warranty_settlements.py`, `tests/test_cierre_marcas.py` | Versión de la rama: es la de `main` **más** la garantía propia como tercer casillero (`warranty_type = 2`, migración 0026, que `main` todavía no tenía). |
| `.gitignore`, `docs/plan-importacion-ciberbrain.md` | Versión de la rama (superconjunto de `main`). |

El merge se hizo en un **worktree aparte** (`C:\Programacion\_worktrees\vogel-merge`),
no en el directorio de trabajo: así el working tree del otro worker quedó
intacto y el merge se pudo probar antes de subirlo.

**Verificación del resultado del merge** (no sólo de la rama):
- Backend **325 tests en verde** sobre el merge.
- Frontend **62 tests en verde** (12 archivos) y `npm run build` OK.
- **CI de GitHub Actions en verde sobre `main`**: jobs `backend`,
  `mysql-migrations` y `frontend` los tres `success` en el commit `22a2f14`.

**El despliegue.** Las dos apps de staging (`...-staging-backend` y
`...-staging-frontend`) se apuntaron a `main` y se re-desplegaron. La cola de
deploys de Coolify es **compartida entre proyectos**: delante de los nuestros
había deploys de `vogel-gestion-servicios-production` y de
`registro-produccion`, y hubo que esperar.

El backend salió bien a la primera (deploy 1680). El frontend **no**: el deploy
1681 dejó el contenedor viejo sirviendo (el bundle seguía siendo
`index-DODAW9H1.js`, el anterior) y, peor, el nginx de ese contenedor seguía
resolviendo el backend por IPv6 (`upstream: "http://[fd04:36e8:6aaa::17]:8000"`),
con `connect() failed (111)` y algún 500. Al re-desplegar (1683) sí: bundle
`index-COx7kMJw.js` y **cero** upstreams IPv6 en el log del nginx.

**Verificado en el navegador** (después del deploy final):

- "9316 órdenes en esta empresa" en el listado (no "0 órdenes").
- Maestro de técnicos: "45 activos de 45", con los filtros Todos / Activos /
  Desactivados y las acciones Renombrar / Desactivar.
- El combo de técnico de la recepción **abre debajo del campo** con los
  técnicos activos, y filtrando "allad" aparece "Alladio".
- El menú tiene las tres secciones juntas: Cierre a marcas, Técnicos y
  Consumo de IA (la que traía `main`).
- La sesión sobrevive a una recarga completa de la página (por el refresh token
  con empresa), y el listado sigue con las OTs de CiberBrain (#9316, #9315, ...).


**Ojo con producción.** Las apps de producción de este repo
(`api.servicios.vogelconsultoria.com.ar` y `servicios.vogelconsultoria.com.ar`)
siguen la rama `main`, así que **el merge a `main` también llegó a producción**
(ya había un deploy de producción en la cola). Lo que llega:

- Migraciones **0026** (dos columnas con default 0) y **0027** (dos
  permisos nuevos). Las dos son **aditivas**: no recalculan ni borran nada.
- La tabla `technicians` la crea la 0024, que ya estaba en `main`.
- El menú **"Técnicos"** va a aparecer para los Administradores, con el
  maestro **vacío**: los datos de CiberBrain están sólo en la base de
  staging, en producción no se importó nada.

Lo que **no** cambia en producción: el `nginx.conf` con `ipv6=off` ya estaba
en `main` (es idéntico al de la rama), y el destino del backend se inyecta
en build por app, así que cada entorno sigue apuntando a su propio alias.

---


## 6. Pendientes

- [x] **Puerto público de la base de staging cerrado** (`is_public=false`, `public_port=''`): se abrió para diagnosticar el listado y quedó cerrado al terminar.
- [ ] Agregar `vue-tsc --noEmit` al frontend (no hay type-check en el build: por eso pasó el
      import faltante de `apiDelete`).
- [x] Merge de `feature/cyberbrain-migracion` a `main` (commit `22a2f14`, CI en verde) y staging
      restaurado a `main`: la base de staging quedó en `20261023_0027` y `main` ahora también
      llega a `0027`.
- [ ] Limpiar las variables duplicadas de `staging-backend` (`CORS_ORIGINS` con dos valores).
- [ ] Decidir qué hacer con el `datadir` viejo de la base de staging.
- [x] La base de producción: nadie la tocó a mano, pero el deploy de producción tomó `main`
      y aplicó las migraciones 0026 y 0027 (las dos aditivas). El menú **Técnicos** queda
      visible para los Administradores pero con el maestro **vacío**: los datos de CiberBrain
      sólo están en la base de staging.
- [ ] **Issue #115 (GitHub) — Maestro de técnicos**: editar con modal, agregar celular con
      validación (se guarda con `549` si el operador no lo escribe) y búsqueda + paginado en el
      listado. Lo pidió el cliente el 23/10/2026 (tarde), con una captura de la pantalla de
      producción. El issue lleva el detalle técnico, los archivos a tocar y los criterios de
      aceptación.
- [ ] **Issue #116 (GitHub) — Identidad de la empresa y versión real**: logo por empresa
      (subida desde Empresas, visible en el comprobante y el presupuesto impreso y en toda la
      app, con el logo de Vogel Consultoría más chico) y que la versión que muestra el pie del
      menú lateral sea la del build desplegado y no un texto fijo.

### 6.1 Un detalle del issue #115: el buscador no se ve en la captura del cliente

En la captura de la pantalla "Técnicos" de producción, arriba de la tabla **no aparece el campo
de búsqueda** ni los chips "Todos / Activos / Desactivados", aunque el bundle desplegado
(`assets/index-COx7kMJw.js`) sí los renderiza: el `.toolbar` del encabezado (`frontend/src/views/TecnicosView.vue:139-169`)
está en el DOM y el CSS de `.page-header` no lo oculta en escritorio.

Lo que sí se ve en la captura es la card de "Agregar un técnico" con el botón "+ Agregar"
**estirado a media pantalla**: no es un botón de contenido, es un ítem de grid (`.field__row` es
`display:grid` con `repeat(auto-fit,minmax(200px,1fr))`), y los ítems de grid se estiran. O sea:
la captura es de esta misma app y no de otra pantalla.

Al implementar #115 hay que confirmarlo (que el buscador quede a la vista) y no dar por hecho que
ya estaba.

### 6.2 La versión "v0.2" es un texto escrito a mano (issue #116)

El pie del menú lateral muestra `v0.2 · Modo Empresa` y el cliente se quejó de que "la versión
nunca se actualiza". Confirmado: **no hay ninguna fuente de verdad de la versión** en el repo.

- `frontend/src/components/Sidebar.vue:168` → `v0.2` está **escrito en el template**.
- `frontend/package.json` → `"version": "0.2.0"`, sin bumpear.
- `backend/app/main.py:17` → `/health` devuelve sólo `{"status":"ok"}`.
- `frontend/Dockerfile` → los únicos `ARG` son `VITE_API_URL` y `BACKEND_INTERNAL_URL`: el build no
  recibe versión ni commit. `docker-compose.yml` → `build.args` con esas dos.

En este repo **no existe `release_notes.txt`** (esa costumbre es de otro proyecto): el changelog
que ve el piloto no sale de acá. El plan del #116 es: un `VERSION` en la raíz, hornearlo en el
build (`ARG VITE_APP_VERSION` / `VITE_APP_COMMIT`), que `/health` lo devuelva también, y usar el
`-Expected` que ya tiene `scripts/verify-deploy.ps1` para comprobar que el bundle servido trae la
versión del release.
