# Sesión 2026-10-25 — Maestro de áreas, garantía y empresa a liquidar de la orden

Objetivo de la sesión: que se pueda **marcar una orden como garantizada y a qué empresa
corresponde**, para que después entre en el **cierre mensual a marcas**.

La pregunta con la que arrancó fue: *"¿en ningún lado puedo poner la empresa ni si
corresponde a garantía o no?"*. La respuesta corta era que no: **no existía ningún lugar**,
y no porque faltara un campo en un formulario.

**Estado al terminar:**

- Maestro de áreas de trabajo (marca + política) completo: API + pantalla, con permisos
  `work_areas.view` / `work_areas.manage`.
- La orden acepta un área: de ella salen la **garantía** y la **empresa a liquidar**.
- La ficha de la orden muestra las dos cosas y deja corregirlas, dejando rastro.
- Backend **364 tests en verde**, frontend **100 tests en verde**.

---

## 1. Por qué no había dónde ponerlo

En el legacy (CiberBrain) la garantía y la empresa a liquidar **no son campos de la
orden**. Son tres tablas encajadas —`dbo.Areas`, `dbo.TiposTrabajos` y
`dbo.Aux_PoliticasxArea`— y las dos cosas que el cierre necesita salen de la **política
del área**:

| Dato | Dónde vive | Qué significa |
|---|---|---|
| Área / marca + política | `work_areas` | Ej. `WHIRLPOOL GARANTÍAS` + `AGU` |
| **Empresa a liquidar** | `work_areas.billing_customer_id` | Cliente al que se le liquida. `NULL` = a nadie |
| **Tipo de garantía** | `work_areas.warranty_type` | 0 fuera, 1 de terceros, 2 propia / de service |
| Enganche OT ↔ área | `work_orders.work_area_id` | Es lo que une la orden con el cierre |

El cierre (`app/services/warranty_settlements.py`) hace JOIN por `work_area_id` y exige
`billing_customer_id IS NOT NULL` + `completed_at` dentro del período.

El hueco era que **`work_areas` solo existía importado del legacy**:

- No había endpoint: `work_areas` no estaba en `backend/app/api/v1/router.py`.
- No había pantalla: no existía ninguna vista de áreas o marcas en el frontend.
- `WorkOrderInput` no tenía `work_area_id` (`backend/app/api/v1/work_orders.py`), ni
  `crear_orden` lo aceptaba (`backend/app/services/work_orders.py`).
- No había forma de editar el área de una orden ya abierta, ni la ficha mostraba la
  garantía.

**Consecuencia:** una orden creada en la aplicación nacía con `work_area_id = NULL`, el
JOIN del cierre la descartaba, y **no aparecía nunca en "Cierre a marcas"**. Las que
entran eran solo las importadas del legacy.

El importador de planillas ("Importar trabajos") tampoco servía: lee la columna
*Garantía* del Excel pero la guarda **dentro de las notas** de la orden
(`backend/app/services/work_order_import_service.py`), no como área.

---

## 2. Qué se entregó

### Backend

| Qué | Dónde | Nota |
|---|---|---|
| Tipos de garantía y su equivalencia | `backend/app/core/warranty.py` | `warranty_type` → `warranty_status`; un solo lugar para la regla |
| Permisos `work_areas.view` / `work_areas.manage` | `backend/app/core/permissions.py` | |
| Migración de permisos | `backend/alembic/versions/20261025_0030_permisos_work_areas.py` | patrón de la 0027; concede a "Administrador" |
| API del maestro | `backend/app/api/v1/work_areas.py` | `GET/POST /work-areas`, `PATCH /work-areas/{id}` |
| Área en la orden | `backend/app/api/v1/work_orders.py` | `work_area_id` en `WorkOrderInput`; `PATCH /work-orders/{id}/work-area` |
| Área al crear la orden | `backend/app/services/work_orders.py` | `crear_orden(..., work_area_id=...)` y `asignar_area(...)` |
| La orden muestra la garantía y la empresa | `backend/app/api/v1/work_orders.py` | `_read` devuelve `warranty_label`, `billing_customer_name`, etc. |
| Tests | `backend/tests/test_work_areas.py` | 9 tests |

### Frontend

| Qué | Dónde |
|---|---|
| Pantalla del maestro | `frontend/src/views/AreasView.vue` (+ `IconAreas.vue`) |
| Combo autocomplete | `frontend/src/components/WorkAreaPicker.vue` |
| Tipo y caché del maestro | `frontend/src/lib/work-areas.ts` |
| Ruta y link | `frontend/src/router.ts`, `frontend/src/components/Sidebar.vue` |
| Campo en la recepción | `frontend/src/views/WorkOrdersView.vue` |
| Panel "Garantía y liquidación" en la ficha | `frontend/src/views/WorkOrdersView.vue` |
| Tests | `frontend/src/__tests__/work-areas.test.ts` (11 tests) |

---

## 3. Decisiones

- **En la orden se elige el área, no la garantía ni la empresa.** Es la única forma que
  funciona con el cierre actual, porque el cierre lee esos dos datos **desde el área**
  (`warranty_settlements.py`). Si se duplicaran sueltos en la orden, la orden y el cierre
  podrían discrepar sin que nadie lo note.
- **La garantía de la orden es una copia de la del área**, como en el legacy
  (`dbo.CS_PoliticasxArea.Garantia`, no el flag crudo de la OT). Por eso, si un área
  cambia de tipo de garantía, las órdenes que la usan se sincronizan: la garantía vieja
  no puede quedar dando vueltas.
- **Sin área la orden se crea igual.** Lo que no tiene es garantía asignada ni empresa a
  liquidar, y eso se dice explícito en pantalla. No se frena la recepción por eso: puede
  ser una orden de trabajo que no se liquida.
- **Pero un texto que no existe en el maestro sí frena el envío.** Es la diferencia entre
  "no elegí un área" y "creí que elegí una y no era ninguna": lo segundo se avisa, no se
  guarda en silencio.
- **El código del área se deriva del nombre** si el operador no escribe uno. El código
  junto con la política es la clave única dentro de la empresa; dos políticas de la misma
  marca necesitan códigos distintos, y el error lo dice.
- **El importador de planillas no se tocó**: los archivos de
  `backend/scripts/import_cyberbrain/` los está escribiendo otra sesión en paralelo sobre
  el mismo repo.

### Tres avisos que cuestan plata si se ignoran

1. **Entra al cierre toda orden que tenga empresa a liquidar, no solo la "garantizada".**
   La garantía solo parte el reporte en tres casilleros. En el corte 2020+ son 6.418
   órdenes con empresa por 73,2 M de costo: 2.853 de garantía estricta y 3.565 de trabajo
   fuera de garantía que la marca igual paga. Filtrar por "es garantía" deja más de la
   mitad de la plata afuera.
2. **Se liquida el COSTO (`cost_total`), no la venta.** En garantía de terceros el legacy
   infla el precio (venta ≈ 2× costo), por eso con la venta el número no cierra.
3. **El corte es por `completed_at`**, no por `received_at`: la orden tiene que estar
   terminada dentro del mes que se liquida.

---

## 4. Bugs encontrados y cómo se diagnosticaron

### 4.1 El combo no leía lo que se escribía

**Síntoma:** el test "filtra por texto sin distinguir mayúsculas ni acentos" falló con
`expected true to be false`: al escribir "garant" seguían apareciendo las dos áreas.

**Causa:** el input usaba `:value="texto"` con `@input="escribir"`, y `escribir()` leía
`texto.value` —que nunca se actualizaba porque el `value` estaba atado por una prop, no
por `v-model`. El texto escrito no llegaba nunca al filtro.

**Cómo se arregló:** el manejador toma el valor del evento
(`texto.value = (ev.target as HTMLInputElement).value`) antes de filtrar. Lo encontró el
test, no el build: `npm run build` es `vite build` **sin `vue-tsc`**, así que un handler
que no lee el input no lo detecta nadie.

### 4.2 La consecuencia de elegir un área no se veía

**Síntoma:** el test "elegir un área de la lista guarda su id y muestra a quién se
liquida" falló: `expected '×' to contain 'Se liquida a DREAN S.A.'`.

**Causa:** el texto de abajo ("Garantía de terceros · Se liquida a DREAN S.A.") se
calculaba a partir de `props.modelValue`. El componente emitía `update:modelValue`, pero
el padre lo aplica en su propio tick: en el test quedó mostrando el estado anterior.

**Cómo se arregló:** el picker guarda el área elegida en un `ref` propio y lo usa para
calcular la consecuencia, con la prop como respaldo. Así la consecuencia no depende de
que el padre reaccione.

### 4.3 El filtro no buscaba por la empresa a liquidar

**Síntoma:** el test no encontraba el área escribiendo "drean" (el nombre de la marca que
se liquida).

**Causa:** el filtro comparaba solo la etiqueta del área. Pero en la planta se conoce la
marca, no el código de la política: buscar por "DREAN" tiene que encontrar el área.

**Cómo se arregló:** el filtro mira la etiqueta, el código **y la empresa a liquidar**.

### 4.4 El `modelValue` del picker era obligatorio

**Síntoma:** `Invalid prop: type check failed for prop "modelValue". Expected Number |
Null, got Undefined` en la suite del frontend.

**Causa:** la prop era obligatoria, y en el detalle de la orden el picker se monta antes
de que haya orden abierta.

**Cómo se arregló:** la prop pasa a ser opcional con `default: null`.

### 4.5 La rama del repo se movió bajo los pies

La sesión paralela de despliegue movió la rama varias veces (`feat/version-build-desplegado`
→ `docs/sesion-2026-10-25-version-build` → `main`), y los cambios que no estaban
commiteados quedaron sobre `main`. Se creó la rama propia
`feat/areas-garantia-liquidacion` y se commiteó antes de seguir.

---

## 5. Cómo se usa

### Dar de alta un área

1. Menú **Operación → Áreas y garantías** → **+ Nueva área**.
2. Cargar: marca (ej. `WHIRLPOOL GARANTÍAS`), política (ej. `AGU`, vacío = principal),
   **empresa a liquidar** (se busca en la lista de clientes) y **tipo de garantía**.
3. Guardar.

El código se deriva del nombre si no se escribe. Dos políticas de la misma marca
necesitan códigos distintos: si se repite, avisa.

### Marcar una orden

**En la recepción:** el campo **"Área / política (garantía y empresa a liquidar)"**. Al
elegir, abajo aparece qué se está eligiendo: *"Garantía de terceros · Se liquida a DREAN
S.A."*. Si el área no tiene empresa a liquidar, avisa que la orden no va a entrar al
cierre.

**En una orden ya abierta:** el panel **"Garantía y liquidación"**, que muestra el área,
la garantía y a quién se liquida, y deja cambiarlas. El cambio queda en el historial de
la orden, con la empresa a liquidar escrita.

---

## 6. Verificación

- Backend: `pytest` → **364 passed** (9 nuevos en `test_work_areas.py`).
- Frontend: `vitest run` → **100 passed** (11 nuevos en `work-areas.test.ts`).
- Frontend: `vite build` OK.
- La integración con el cierre está probada de punta a punta en
  `test_work_areas.py::test_sin_area_la_orden_no_entra_al_cierre_y_con_area_si`: dos
  órdenes idénticas, una con área y otra sin; al generar el cierre de 2025-06 entra
  **solo** la que tiene área, por 250 de costo, en el casillero de garantía de terceros.

### Publicación

PR **#125** (`feat/areas-garantia-liquidacion` → `main`), mergeado en `1b7db03`.

CI: **backend, frontend y `mysql-migrations` en verde**. El check de migraciones corre la
migración contra **MySQL real**, así que la `20261025_0030` ya quedó verificada fuera del
SQLite de los tests.

Producción se autoplojea al mergear a `main`; staging es manual y hubo que dispararlo.

| Ambiente | Verificación | Resultado |
|---|---|---|
| producción | `scripts/verify-deploy.ps1 -Expected "area-picker__option"` | OK — bundle nuevo, API `401 json`, modo cross-origin |
| producción (backend) | `openapi.json` de `api.servicios…` | las 3 rutas nuevas presentes |
| staging (frontend) | `scripts/verify-deploy.ps1 -Expected "area-picker__option" -Wait` | OK — bundle nuevo, API `401 json`, modo same-origin |
| staging (backend) | `openapi.json` del backend | las 3 rutas nuevas presentes |

El marcador `area-picker__option` es una clase CSS que **solo existe en el código
nuevo**: sirve para distinguir un bundle realmente nuevo de uno viejo. Un 200 en la
página no alcanza para dar el deploy por bueno.

Antes de disparar el deploy de staging se verificó que las cuatro apps de Coolify
tienen `git_commit_sha = HEAD` (si estuviera anclado a un SHA viejo, el deploy manual
construye ese commit viejo).

### Validación en pantalla, con los datos reales

Con Playwright contra **staging** y la empresa **Electrotecniref** (3), que tiene **126
áreas** del legacy ya cargadas y 9.316 órdenes. Las dos resoluciones que usa el cliente:
**1638x969** y **1366x768**.

| Qué | Resultado |
|---|---|
| Maestro de áreas | Lista las 126 áreas con su código, política, empresa a liquidar, garantía y estado. El menú lateral muestra "Áreas y garantías" en Operación y "Cierre a marcas" en Finanzas. |
| Recepción | El campo "Área / política" queda entre Equipo y Técnico. Escribir "alladio" filtra a las 7 políticas de Alladio, y cada opción muestra su garantía y su empresa. Al elegir, abajo queda escrito "Garantía de terceros · Se liquida a JOSE M. ALLADIO E HIJOS S.A.". |
| Ficha de la orden | El panel "Garantía y liquidación" muestra área, garantía y empresa de la OT #9307 (DREAN GARANTIAS → Garantía de terceros → DREAN S.A.), con el combo para corregirlo. |
| Modal de recepción | Scrollea dentro del modal: a 1366x768 el contenido excede la ventana, pero el modal tiene `max-height:92vh` y `overflow:auto`, así que nada queda apretado ni superpuesto. |

**Un defecto se encontró así y se corrigió:** el panel de la ficha se armaba en **tres
columnas**, y en el ancho real de la columna lateral (unos 330 px) "Garantía de terceros"
quedaba partido en tres líneas. Pasó a una sola columna, igual que las tarjetas vecinas
(Fechas, Recepción, Cliente y equipo) — PR **#127**.

---

## 7. Pendientes

- [x] **Migración `20261025_0030` verificada contra MySQL real**: el check
      `mysql-migrations` de la CI la corre contra un MySQL de verdad, y quedó aplicada en
      staging y producción con el deploy (el arranque del contenedor es
      `alembic upgrade head`).
- [ ] **Dar los permisos a los demás roles** desde *Roles y permisos*: `work_areas.view`
      para ver el maestro y `work_areas.manage` para dar de alta y editar áreas. La
      migración solo los concede a "Administrador".
- [ ] **El importador de planillas sigue sin traer el área**: las órdenes que entran por
      "Importar trabajos" (Excel) siguen naciendo sin área, y por lo tanto fuera del
      cierre. El archivo lo está escribiendo otra sesión; cuando se libere, el cambio es
      leer una columna de área (o de empresa a liquidar) y mapearla a `work_area_id`.
- [ ] **El importador del legacy (CiberBrain) ya trae el área** (`work_area_id` y
      `warranty_status` los escribe `backend/scripts/import_cyberbrain/steps/work_orders.py`),
      así que esas órdenes sí entran al cierre. No se tocó ese importador.
- [ ] **Revisar las áreas que ya quedaron cargadas del legacy** a la luz del maestro nuevo:
      si el importador dejó áreas sin empresa a liquidar, no entran al cierre.
- [ ] **En la tabla de órdenes no se ve el área**: el listado muestra cliente, equipo,
      falla y estado. Si hace falta filtrar por marca o por "pendiente de liquidar", es
      un filtro más en `WorkOrdersView`.
