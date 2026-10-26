# Sesión 2026-10-26 — Finalización técnica: por qué una orden en garantía no llegaba al cierre

Objetivo de la sesión: que la orden que el usuario ya había marcado como **garantía y con
empresa a liquidar** aparezca efectivamente en el **cierre mensual a marcas**.

La pregunta con la que arrancó: *"como es esto, le puse garantía briket pero voy a liquidar
y no está eso para liquidar"*.

**Estado al terminar:**

- Regla de backend: al entregar una orden **con costo cargado**, se registra también la
  **finalización técnica**.
- Acción manual para registrarla, que **funciona aunque la orden ya esté entregada**
  (estado final), con fecha a elección y con rastro en el historial.
- Aviso en la ficha de la orden: *"Sin finalización técnica esta orden no entra al cierre a
  marcas"*.
- **El cierre ahora ve el costo de las OTs cargadas en la app**: antes las leía como $0.
- **El total del cierre no se queda en $ 0,00** al cambiar de mes, y no muestra el mes
  equivocado.
- Backend **376 tests en verde** (12 nuevos), frontend **106 tests en verde** (6 nuevos).

---

## 1. El diagnóstico: la orden estaba bien marcada, y aun así no se liquidaba

La OT del usuario es la **#9316** (recibida 21/10/2026, entregada 26/10/2026, equipo
"HELADERA BRIKET ILEGIBLE", técnico Suárez Pablo, línea LABOR "Se arreglo la pruert",
costo 16.000, venta 18.000).

La orden **estaba bien marcada**:

- Área `BRIKET GARANTIAS` → garantía de terceros → se liquida a `BRIKET S.A.`
- Evento `WORK_AREA_CHANGE` del 26/10 18:31:29: el área pasó de `BRIKET GARANTIAS · FUERA`
  a `BRIKET GARANTIAS`.

Y aun así no aparecía en el cierre. La causa estaba en otro lado:

| Dato | Valor | Por qué importa |
|---|---|---|
| `completed_at` | **NULL** | El cierre filtra por este campo, no por `delivered_at` |
| `delivered_at` | 26/10/2026 18:32 | La orden sí se entregó |
| Estado | "Entregado" (id 8) | `marks_delivered=True`, pero `marks_completed=False` |
| "Listo" (id 7) | — | el único estado con `marks_completed=True` |

O sea: la orden **salteó de "Recibido" a "Entregado"** (evento `STATUS_CHANGE`: *"Estado
cambiado de Recibido a Entregado. Se registró la entrega real al cliente."*), y como
"Entregado" no marca finalización técnica, `completed_at` quedó vacío. El cierre exige
`completed_at` dentro del período, así que la orden **no entraba en ningún mes**.

El filtro del cierre, textualmente (`backend/app/services/warranty_settlements.py`):

```python
WorkOrder.completed_at.isnot(None),
WorkOrder.completed_at >= desde,
WorkOrder.completed_at < hasta,
```

### El callejón sin salida

"Entregado" tiene `is_final=True`, y `cambiar_estado` bloquea el cambio con 409 (*"La orden
de trabajo está en un estado final (entregada) y no puede cambiar de estado."*). Tampoco se
podía tocar el área ni la fecha de entrega en estado final. `completed_at` solo lo escribía
el paso a un estado con `marks_completed`. Es decir: **una orden entregada sin pasar por
"Listo" quedaba afuera del cierre para siempre, sin forma de corregirla.**

Por eso la decisión fue **regla de backend + corrección manual**, y no tocar los flags de
los estados: `marks_completed` es un flag **exclusivo** (`EXCLUSIVE_STATUS_FLAGS`), y
ponerlo en "Entregado" sacaría a "Listo" del mapa y movería el contador `ready_to_deliver`
del dashboard (`marks_completed and not marks_delivered`).

### Daño colateral que se revisó

El campo "garantía" que se ve en la orden (#9307) decía `BRIKET GARANTIAS · FUERA` y
después `BRIKET GARANTIAS`: el texto de garantía de la OT es una **copia** del área, y la
que manda es el área. No se cambió: la copia se sincroniza sola cuando cambia el área
(`PATCH /work-areas/{id}`).

---

## 2. Qué se entregó

### Backend

| Qué | Dónde | Nota |
|---|---|---|
| `tiene_costo_cargado(db, orden)` | `backend/app/services/work_orders.py` | `cost_total` > 0, o el costo de las líneas — **preguntado al mismo servicio que usa el cierre**, para que no discrepen |
| `registrar_finalizacion_tecnica(...)` | `backend/app/services/work_orders.py` | Escribe `completed_at` + evento `TECHNICAL_COMPLETION`. **No bloquea el estado final** |
| Regla al entregar | `backend/app/services/work_orders.py` (`cambiar_estado`) | Si el estado destino marca entrega, no hay finalización técnica y **hay costo cargado**, se registra sola |
| Endpoint | `backend/app/api/v1/work_orders.py` | `POST /work-orders/{id}/technical-completion` (con `completed_at` opcional y `note`) |
| `costo_desde_lineas(...)` | `backend/app/services/warranty_settlements.py` | El cierre ahora suma **las dos** fuentes de líneas: las del legacy y el trabajo registrado en la app |
| Tests | `backend/tests/test_finalizacion_tecnica.py` | 12 tests |

### Frontend

| Qué | Dónde |
|---|---|
| Botón "Registrar" en la tarjeta **Fechas** | `frontend/src/views/WorkOrdersView.vue` |
| Aviso + botón en el panel **Garantía y liquidación** | `frontend/src/views/WorkOrdersView.vue` |
| Modal con fecha y observación | `frontend/src/views/WorkOrdersView.vue` |
| Hora de empresa → UTC | `frontend/src/views/WorkOrdersView.vue` (`companyLocalToUtc`) |
| Rótulo del evento en el historial | `TECHNICAL_COMPLETION` → "Finalización técnica" |
| El contador del cierre sigue al dato | `frontend/src/lib/motion.ts` |
| La carga del cierre ignora respuestas viejas | `frontend/src/views/CierreMarcasView.vue` |
| Tests | `frontend/src/__tests__/finalizacion-tecnica.test.ts` (4) y `motion.test.ts` (2 nuevos) |

---

## 3. Decisiones

- **La regla se dispara solo cuando hay costo cargado.** Una orden sin costo no tiene nada
  que liquidar, y darla por finalizada sería dar por hecho un trabajo que no se cargó. El
  resto se resuelve con la corrección manual.
- **La corrección manual sí funciona en estado final.** Es lo que hace falta: el caso real
  es una orden **ya entregada** que quedó sin finalización técnica. Cambiar el área o la
  fecha de entrega dan 409 en estado final; esta no, porque es un dato del trabajo hecho,
  no un cambio de estado.
- **La fecha se puede elegir, y es la que decide el período.** Sin eso, corregir una orden
  de septiembre en octubre la mandaría al cierre equivocado. Por defecto el modal propone
  la fecha de la **entrega real** (cuando terminó el trabajo), que es lo más cercano a la
  verdad.
- **La hora que escribe el operador es la de la empresa, y se guarda como UTC.** El cierre
  agrupa por mes: un corrimiento de horas puede dejar la orden en el mes que no es. Por eso
  el modal convierte con la zona de la empresa (`companyTimezone`) en lugar de usar la del
  navegador.
- **No se toca `marks_completed` de "Entregado"**: los flags son exclusivos y ese cambio
  rompería el contador de "listos para entregar" del dashboard.
- **La corrección queda en el historial**, con la fecha y la observación: es un cambio de
  criterio sobre una orden ya cargada y tiene que verse.

---

## 4. Bugs encontrados y cómo se diagnosticaron

### 4.1 El test leía el input equivocado

**Síntoma:** el test "registra la finalización técnica con la fecha de la entrega real"
falló con `expected '' to be '2026-10-26T18:32'`.

**Causa:** el selector `input[type="datetime-local"]` encontraba el **primero** del DOM, que
es el de "Entrega prevista" (que está vacío porque no hay fecha prevista), no el del modal.

**Cómo se arregló:** el input del modal lleva `aria-label="Fecha de finalización técnica"` y
el test lo busca por ese nombre. No es solo un detalle de test: en la pantalla hay dos
inputs de fecha en la misma tarjeta, y sin un nombre propio no se distinguen.

### 4.2 La fecha del modal era la del navegador, no la de la empresa

**Causa (detectada al escribir el código, no por un fallo):** el patrón que ya usaba la
pantalla para "Entrega prevista" (`new Date(input.value).toISOString()`) interpreta el
`datetime-local` en la zona **del navegador**. Si el navegador no está en la zona de la
empresa, la fecha guardada se corre.

**Cómo se arregló:** `companyLocalToUtc()` convierte la hora escrita (hora de la empresa)
a UTC usando la zona de la empresa, con dos vueltas para que el horario de verano no
desplace el resultado. La prueba lo verifica: 26/10 18:32 hora de Córdoba → `21:32Z`.

### 4.3 El cierre leía las líneas de la tabla equivocada

**Síntoma:** después de registrar la finalización técnica de la OT #9316, la orden **apareció**
en el cierre de octubre (BRIKET S.A. pasó de 3 trabajos a 4) pero con **$ 0**.

**Causa:** el cierre saca el importe de dos lugares: `work_orders.cost_total` (que llena el
importador del legacy) y, si ese está en cero, de las **líneas**. Pero leía las líneas de
`work_order_parts`, que es la tabla del **legacy**. Las OTs hechas en la app guardan el
trabajo en otra tabla: `work_order_execution_items` (workorder_execution_items). Como las
OTs de la app no tienen partes —y su `cost_total` es 0—, **todas entraban al cierre con
cero**. El docstring de la función decía "las OTs nacidas en el sistema nuevo no traen
`cost_total`: sale de las lineas", pero esas líneas nunca se leyeron.

**Cómo se diagnosticó:** comparando el detalle de la OT con el cierre. La OT #9316 tiene una
línea de ejecución (LABOR, costo 16.000, precio 18.000) y ningún `cost_total`; el cierre
devolvía 0.

**Cómo se arregló:** `costo_desde_lineas()` ahora suma **las dos** fuentes de líneas (las del
legacy y el trabajo registrado en la app). No hay doble conteo en la práctica: una OT
importada trae `cost_total` y no llega a este camino, y una OT hecha en la app no tiene
partes del legacy. Y `tiene_costo_cargado()` —la pregunta que hace la regla al entregar—
ahora usa **el mismo servicio**, para que la regla y el cierre no puedan discrepar.

### 4.4 El total del cierre se quedaba en $ 0,00 al cambiar de mes

**Síntoma:** al abrir el cierre de octubre, la tabla mostraba los importes por empresa
(DREAN 136.400,84, BGH 119.834,72…) pero el encabezado decía **"Total a liquidar $ 0,00"**,
y en los tres casilleros de garantía también $ 0,00. Al recargar y volver a cambiar de mes,
ya salía bien: era intermitente.

**Causa:** el número grande no lo pinta Vue, lo pinta una cuenta-up con GSAP
(`data-count`). Cuando se cambia de mes, la cuenta anterior se corta
(`ctx.revert()` en `useReveal`) y **GSAP devuelve el contador a su valor inicial (0) y
dispara el `onUpdate`**: el elemento queda escrito con "$ 0,00". Después, la cuenta nueva
arranca "desde el valor anterior" y su `onComplete` ponía el texto que había leído del DOM
— que ya era el "$ 0,00" corrupto. O sea: el valor roto se congelaba.

Además, la cuenta vieja seguía escribiendo después de que Vue pintara el dato nuevo, así
que podía pisar el número correcto.

**Cómo se diagnosticó:** con dos tests en `motion.test.ts` que reproducen el caso exacto
(el corte de la cuenta anterior y el cambio de dato durante la cuenta). Los dos fallaban
con "$ 0,0" antes del arreglo.

**Cómo se arregló:**
- El texto final se arma **desde el dato** (`data-count`, `data-decimals`, `data-prefix`) y
  no desde el DOM: leer el DOM congelaba el valor roto.
- La cuenta **sigue al dato**: si `data-count` cambió, esa cuenta deja de escribir.

### 4.5 El cierre podía mostrar el mes equivocado

**Síntoma:** al cambiar de mes rápido, la pantalla mostraba los números del mes anterior.

**Causa:** `cargar()` no distingue respuestas: si la petición de septiembre tarda más que
la de octubre, la que responde último gana, y el cierre queda mostrando septiembre.

**Cómo se arregló:** cada carga toma un número y solo la última en pedir puede escribir el
resultado. Se aplicó lo mismo en el listado de órdenes (`WorkOrdersView.load()`), que tenía
el mismo patrón.

### 4.6 `datetime.utcnow()` está deprecado

**Síntoma:** `DeprecationWarning` en la suite del backend.

**Causa:** es el patrón que ya usa el código (`utcnow()` en `work_orders.py`), no algo
nuevo de esta sesión. Se siguió el mismo criterio para no mezclar dos estilos en el mismo
archivo. Queda anotado como deuda.

---

## 5. Cómo se usa

1. Abrir la orden.
2. En la tarjeta **Fechas**, la fila **"Finalización técnica"** dice "Pendiente" y tiene un
   botón **Registrar**. Si la orden tiene empresa a liquidar, el panel **"Garantía y
   liquidación"** avisa: *"Sin finalización técnica esta orden no entra al cierre a
   marcas"*, con un botón para registrarlo.
3. En el modal: se elige la **fecha** (por defecto, la de la entrega real) y, si hace falta,
   una observación. **Registrar**.
4. La orden entra al cierre del período de esa fecha, y el cambio queda en el historial.

Desde ahora, una orden que se entrega con costo cargado **registra la finalización técnica
sola**: no hay que hacer nada.

---

## 6. Verificación

- Backend: `pytest` → **376 passed** (12 nuevos en `test_finalizacion_tecnica.py`).
- Frontend: `vitest run` → **106 passed** (4 nuevos en `finalizacion-tecnica.test.ts`,
  2 nuevos en `motion.test.ts`).
- Frontend: `vite build` OK.
- La integración con el cierre está probada de punta a punta:
  `test_la_orden_entregada_entra_al_cierre_a_marcas` (entrega → entra sola) y
  `test_registrar_la_finalizacion_tecnica_a_mano_en_una_orden_entregada` (corrección
  manual → entra con 16.000 a `BRIKET S.A.`).
- `test_la_fecha_registrada_decide_el_periodo_del_cierre` deja la orden en **septiembre** y
  comprueba que entra en el cierre de septiembre y **no** en el de octubre.
- `test_una_orden_cargada_en_la_app_se_liquida_con_el_costo_de_su_trabajo` cubre el costo de
  las OTs hechas en la app (16.000, no 0).
- En **staging**, con los datos reales: la OT #9316 pasó de no aparecer a aparecer en el
  cierre de octubre con su costo, y el evento `TECHNICAL_COMPLETION` quedó en el historial.

---

## 7. Pendientes

- [ ] **Dar los permisos a los demás roles** desde *Roles y permisos* (`work_areas.view`,
      `work_areas.manage`): la migración solo los concede a "Administrador".
- [ ] **El importador de planillas sigue sin traer el área**: las órdenes que entran por
      "Importar trabajos" (Excel) nacen sin área y quedan fuera del cierre. El archivo lo
      está escribiendo otra sesión en paralelo.
- [ ] **Revisar las áreas del legacy** que quedaron sin empresa a liquidar: no entran al
      cierre.
- [ ] **En la tabla de órdenes no se ve el área**: si hace falta filtrar por marca o por
      "pendiente de liquidar", es un filtro más en `WorkOrdersView`.
- [ ] **Una orden sin costo cargado que se entrega sigue sin finalización técnica** a
      propósito. Si alguna vez hay que liquidarla, se registra a mano.
- [ ] **La OT #9316 se corrigió en staging, no en producción**: la credencial de producción
      que figura en `docs/sesion-2026-10-22-cierre-marcas.md` devuelve 401 y no hay ninguna
      otra a mano. En producción hay que corregirla con el botón nuevo (o con una sesión
      válida).
