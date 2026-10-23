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

**Por qué no lo管理局 el test:** jsdom no calcula posiciones, así que en el test el menú
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

### 5.3 El listado mostraba "0 órdenes" (no era el backend)

Lo primero que se hizo fue llamar a la API de staging **como el navegador**: login real
(`admin@electrotecniref.com.ar`), `POST /auth/select-company` con la empresa 3 y después
`GET /work-orders?page=1&page_size=25`. La respuesta fue **200 con `total: 9316` y 25
ítems**: el backend estaba bien.

Dos detalles que비용aron tiempo y conviene no repetir:

- **El token del login no trae `company_id`**: sin `POST /auth/select-company`, todo lo que
  sea de empresa responde **409 "Active company required"** (no 401). El login del frontend
  es el que resuelve ese paso.
- **El log de acceso de Coolify no muestra el cuerpo**, solo el estado. Para ver qué recibe
  el navegador hay que llamar a la API con el mismo token (`backup/_work/probe_staging.py`).

Entonces el "0 órdenes" del navegador fue la **ventana del incidente de la base**: el backend
respondía 500 y el frontend se quedaba sin datos. Como defensa se puso la guarda
`Array.isArray(r?.items)` en `load()` y `total` numérico, para que una respuesta inesperada
muestre el estado vacío en vez de romper el render.

**Arreglo:** `load()` ahora valida la forma de la respuesta; `loadStatuses()` tiene
`try/catch`; el deep-link no depende de que las cargas tengan éxito.

---

## 6. Pendientes

- [ ] **Cerrar el puerto público de la base de staging** (`is_public=true`, `public_port=33061`):
      se abrió para diagnosticar el listado y hay que volver a cerrarlo
      (`PATCH /api/v1/databases/diamcot1wyytezyasugd5biv {is_public=false; public_port=''}`).
- [ ] Agregar `vue-tsc --noEmit` al frontend (no hay type-check en el build: por eso pasó el
      import faltante de `apiDelete`).
- [ ] Merge de `feature/cyberbrain-migracion` a `main` y, después, restaurar staging a `main`
      (la base de staging ya está en `20261023_0027`; `main` sólo llega a `0025`).
- [ ] Limpiar las variables duplicadas de `staging-backend` (`CORS_ORIGINS` con dos valores).
- [ ] Decidir qué hacer con el `datadir` viejo de la base de staging.
- [ ] La base de producción sigue sin tocar.
