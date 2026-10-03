# Bitácora 2026-10-03 (tercera tanda): herramientas de escritura con confirmacion humana

Cierra el sub-issue 3 de #44. Es el primero donde la IA propone algo que **cambia el estado del
sistema**, asi que la regla es mas fuerte que en los dos anteriores: no alcanza con que el dato
sea real, tiene que que ninguna escritura ocurra sin que una persona la decida.

## La regla de oro, y como se volvio estructural

**La IA propone, la persona confirma.** Y queda registro de quien propuso, quien confirmo o
corrigio, y que se termino persistiendo.

Lo importante es que no es una convencion sino la estructura: las siete herramientas de
escritura **no escriben**. Dejan una fila en `ai_action_proposals` con estado `pendiente` y le
devuelven al modelo el id, para que le diga al operador que hay algo que confirmar. El modelo
no tiene ninguna via para aplicar una escritura, porque la herramienta no recibe ningun
parametro que pueda escribir.

La confirmacion es otro endpoint, con la sesion de una persona y sus permisos.

Por que no "escribo y despues se revisa": un modelo puede pedir una escritura sobre el cliente
equivocado o con el precio equivocado. Si eso ya esta en la base, deshacerlo es trabajo de
persona. Guardando la propuesta primero, la persona puede **corregir** los argumentos, y se
escribe lo que confirmo.

## Se escribe lo que la persona confirmo

Las dos columnas quedan guardadas: `proposed_arguments` y `confirmed_arguments`. La respuesta
trae `lo_que_cambio`, que es la diferencia entre una y otra. Es el dato mas importante de la
pantalla de confirmacion, porque es ahi donde se ve que la persona le corrigio al modelo.

## El candado: una propuesta se aplica una sola vez

`confirmar` reclama la propuesta con un UPDATE condicional de `pendiente` a `aplicando`. Un doble
clic o un reintento del navegador llega cuando el estado ya no es `pendiente`, y ahi no se
vuelve a escribir: se devuelve el resultado guardado con `ya_se_habia_aplicado: true`.

El estado `aplicando` existe para que, si el proceso se muere a mitad de camino, la propuesta
quede trabada en un estado que un humano tiene que mirar, y no disponible para reintentar solo.
Una fila trabada es mejor que una escritura duplicada.

## El riesgo se calcula al proponer, no al aplicar

- `agregar_repuesto` con precio: `riesgo: financiero`, porque mueve plata.
- `actualizar_ot` a un estado con aviso: `riesgo: comunicacion` y `notifica_cliente: true`. Se
  calcula con `planear_aviso`, que no escribe nada y solo dice que se mandaria.

Un WhatsApp enviado no se puede deshacer. Si eso se supiera despues de aplicar, la persona ya
habria confirmado a ciegas. Por eso el aviso se muestra antes, en la pantalla.

## El costo interno no lo propone la IA

`costo_unitario` no lo rellena el modelo. Es un dato del negocio y ademas la empresa puede
tenerlo oculto del cliente: que la IA pudiera fijarlo seria escribir un dato que ni el operador
ve. La persona lo completa al confirmar.

## Un solo camino de escritura

Se extrajo la logica de dominio a `app/services/work_orders.py` y los handlers de la API
delegan ahi (`crear_ot` y el cambio de estado). Si las propuestas reimplementaran la numeracion
de orden o el encolado de avisos, estarian aplicando reglas que la aplicacion no aplica: un
mismo dominio con dos reglas siempre termina en dos, y la que sobra es la que no tiene tests.

## Permisos

Confirmar exige el permiso de la **herramienta** que se aplica, no solo `ai.use`. Poder usar el
asistente no es poder dar de alta clientes. Sin permiso la propuesta sigue pendiente, para
poder confirmarla mas tarde con alguien que si pueda.

## Verificacion

- `pytest`: **190 en verde** (173 previos + 17 nuevos).
- Las dos garantas centrales probadas **saboteando el codigo**:

| Saboteo | Resultado del test |
|---|---|
| Sacar el `status == PENDIENTE` del UPDATE de reclamo | `test_confirmar_dos_veces_no_duplica` falla: la segunda confirmacion vuelve a escribir |
| Ignorar los argumentos confirmados | `test_confirmar_escribe_lo_que_la_persona_corrijo` falla: escribe lo propuesto |

- Un caso comprueba que **el numero de orden no se reserva** sin confirmacion, que es el detalle
  que delata una escritura encubierta.

## Tres bugs que aparecieron al escribir esto

1. **`db.execute(select(Modelo)).first()` devuelve una Row, no el modelo.** Pasa tres veces en el
   mismo PR, y el sintoma es un `AttributeError` sobre un atributo que existe. Con
   `select(A, B, C)` funciona porque se desempaqueta la tupla; con un solo modelo hay que pedir
   `.scalars()`.
2. **`except` con una clase que no existe en ese modulo** reemplaza el error real por un
   `AttributeError` del propio `except`, y se pierde el motivo por el que fallaba la operacion.
3. **Cambio de estado solo**: mi primer guard rechazaba la propuesta cuando no traia nada mas que
   el estado. Es la accion mas frecuente que hay, y la estaba rechazando.

## Pendientes

- **La UI de confirmacion no existe todavia.** La API trae la propuesta con lo propuesto, lo
  confirmado y lo que cambio, pero la pantalla es el sub-issue #95. Sin ella, las propuestas se
  pueden confirmar por API pero no desde la aplicacion.
- Quedan dos clientes de prueba en staging de la validacion en vivo, para borrar a mano.
- Sub-issues de #44 que siguen abiertos: #91 (este), #92 a #96.
