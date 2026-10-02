# Dashboard: "Requieren atención" navegable (#57)

**Estado:** en curso, 2026-10-02
**Rama:** `feat/issue-57-requieren-atencion`

## Objetivo

Que cada alerta del panel "Requieren atención" sea un acceso directo al listado de las OT
que la disparan, que las categorías se resuelvan con reglas del sistema y no con nombres de
estado, y que haya estado vacío.

## Lo que ya existía y lo que no

El backend ya devuelve los cuatro conteos y el frontend los pinta como texto plano. Falta
todo lo demás, y aparecen dos huecos que no se ven leyendo el issue:

### 1. "Esperando repuesto" se resolvía por el nombre del estado

```python
"waiting_parts": sum(int(r.count) for r in rows if "repuesto" in r.name.lower()),
```

Una empresa que llame al estado "Esperando componente" o "A la espera de material" ve el
contador en 0. El issue pide explícitamente no acoplar las categorías a nombres, así que la
solución es la misma que usa el resto del flujo: un flag semántico en `WorkOrderStatus`.

Agrega `marks_waiting_parts`, con la misma exclusión mutua que los otros flags (un estado
no puede ser a la vez "espera repuesto" y "en reparación").

### 2. El listado no sabe filtrar "abiertas"

Tres de las cuatro alertas se expresan con `status_id` repetido, que el listado ya acepta.
La cuarta ("más de 15 días abiertas") necesita dos cosas que no existen:

- `date_to` filtra por `received_at` y es **inclusivo** (`received_at < date_to + 1 día`),
  así que el borde hay que correrlo un día para que el link no muestre un día de más.
- `date_to` solo no filtra las OTs abiertas: devolvería también las ya entregadas hace un
  mes. Hace falta `open_only`.

Se agrega `open_only` al listado, con la misma regla semántica que ya usa el dashboard
(`is_final` y `marks_delivered` falsos, con `coalesce` para las OTs sin estado).

## El bug que se encontró de paso

`StatusInput` declara todos los flags con default `False`, y `update_status` hace
`setattr` sobre **todos** los campos de `payload.model_dump()`. El editor de estados que
está dentro de la pantalla de OT manda solo siete campos:

```js
apiPatch("/work-orders/statuses/" + st.id, { name, color, sort_order, active,
                                              is_initial, is_final, marks_completed, marks_delivered })
```

Los tres que no manda (`marks_quoted`, `marks_awaiting_quote_approval`, `marks_repair`)
llegan como `False` y **se borran**. Sin ningún test que lo cubra.

El daño no es cosmético: `_move_status` busca el estado destino por flag, así que al
guardar un nombre de estado desde la pantalla de OT se rompe, en silencio:

- el presupuesto ya no mueve la OT al estado de "Presupuestado" (`marks_quoted`);
- enviar un presupuesto con aprobación ya no la mueve a "Esperando aprobación";
- los conteos `quoted` y `awaiting_quote_approval` del dashboard caen a cero.

Se arregla con `exclude_unset=True` en el PATCH, que es lo que un update parcial debería
hacer. El editor de estados de la pantalla de admin manda el objeto completo, así que sigue
fijando todos los flags. Es el mismo arreglo que evita que el flag nuevo herede el defecto.

## Forma de la respuesta

`attention` deja de ser un diccionario de números y pasa a ser una lista de categorías con
su destino, para que el frontend no tenga que reconstruir la regla:

```json
"attention": [
  { "key": "awaiting_quote_approval", "count": 3, "status_ids": [4] },
  { "key": "waiting_parts",           "count": 1, "status_ids": [5] },
  { "key": "ready_to_deliver",        "count": 2, "status_ids": [7] },
  { "key": "older_than_15_days",      "count": 4, "date_to": "2026-09-16", "open_only": true }
]
```

La etiqueta en español la sigue poniendo el frontend, por `key`: el backend decide **qué
cuenta**, la pantalla decide **cómo se nombra**. Así una empresa que renombra estados no
termina con textos que no coinciden.

## El criterio que manda: el link tiene que cuadrar

El riesgo real de este issue es un contador que dice 4 y un link que lleva a 37 resultados.
Por eso la prueba que importa no es "devuelve la fecha correcta" sino:

> seguir el `date_to` + `open_only` que devuelve el dashboard contra el listado tiene que
> dar exactamente el mismo número que el contador de la alerta.

Se prueba para las cuatro categorías, con la cuenta de la lista contrastada contra la del
dashboard.

## Distribución en pantalla

El issue pide que en móvil la sección aparezca inmediatamente después de los indicadores
principales, y en desktop una zona visible sin generar una pantalla de tarjetas
decorativas. Se resuelve con una franja de ancho completo apenas debajo de los KPIs, antes
de "Actividad de hoy", y sacando la tarjeta de "Requieren atención" de la grilla analítica.
La grilla queda con tendencia + antigüedad arriba y la distribución de estados
ocupando el ancho completo abajo, para no dejar un hueco en la columna angosta.

## Fuera de alcance

- El umbral de 15 días sigue siendo un valor definido en el código, que el issue permite
  ("configurable/**definido**"). Hacerlo parámetro por empresa es un paso aparte: implica
  insertar la definición en `ParameterDefinition` y sumarla a la pantalla de parámetros.
- Migrar producción a same-origin sigue pendiente, pero es una variable y no código.
