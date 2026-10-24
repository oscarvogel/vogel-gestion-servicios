# Bitácora 2026-10-04: consumo y facturación del adicional de IA (#44, sub-issue 8)

El último de los ocho. No agrega capacidades al asistente: agrega **la pantalla desde la que se
decide a quién se le renueva el adicional**.

## Qué ya existía y qué faltaba

`ai_usage` viene llenándose desde el sub-issue 1: una fila por pedido al proveedor, con tokens,
costo estimado, estado y fecha, e índice por `(company_id, created_at)` que el propio modelo
describe como *"la consulta de cuota y de facturacion"*. El problema nunca fue que faltaran los
datos: era que no había forma de **leerlos**.

## Dos audiencias, una pantalla

El issue pide dos cosas que parecen de pantallas distintas:

- *"La empresa ve cuanto consumio y cuanto le queda de cuota."* → `/app/consumo-ia`
- *"Historial para la facturacion del adicional."* → la misma pantalla, sección de empresas

Son la misma pantalla porque la regla dura es que **una empresa solo ve lo suyo**, y partirla en
dos rutas hace más fácil que se mezclen. Con empresa activa, cualquiera con `ai.use` ve su mes:
gastado, cuánto queda, desglose por operación e historial. Si además sos superadmin, arriba
aparece el listado de todas las empresas.

El endpoint de la lista es superadmin. Si da 403, la sección se oculta en vez de romper la
pantalla, porque un superadmin en modo plataforma no tiene empresa activa y por lo tanto no
tiene "su" consumo: eso es correcto, no es un error.

## `None` y `0` no son lo mismo

`cuota_restante_usd` devuelve `null` cuando la empresa no tiene tope, y `0` cuando ya lo agotó.
Es la diferencia entre "no tenés límite" y "no te queda nada", y confundirla haría que una
empresa sin techo se viera agotada. Cuando hay tope y se pasó, el restante se topa en `0` y no
baja: un negativo es una invitación a un bug.

El mismo criterio en el tablero: una empresa **sin la IA habilitada pero con consumo** aparece
listada y con un cartel arriba. Es justo la fila que hay que mirar, porque o se le quedó el
interruptor después de un mes de uso, o está pagando sin estar contratada. Filtrar el tablero
por "solo las que tienen la IA prendida" esconde las dos.

## Un bug mío que encontró un test

El historial mensual usaba `fin = _month_start(atras)` y `desde = fin - 1 día`, o sea una
ventana de **un solo día** por mes. El acumulado daba casi siempre cero y no se notaba a simple
vista: los tests anteriores no cubrían el historial.

Ahora el corte va de `_month_start(k)` a `_month_start(k-1)`, que es el mes entero. Los cortes se
calculan en Python y no con `date_trunc` o `strftime` a propósito: la suite corre en SQLite y la
migración en MySQL, y las funciones de fecha no coinciden entre los dos motores. Un rango por
mes funciona en ambos sin una sola función dependiente del motor.

## El estimado y el facturado

El criterio del issue dice que *"el costo estimado se distingue del facturado"*. En el sistema
**no hay cifra facturada**: la factura del proveedor no se carga, no hay de dónde sacarla. Así
que lo que se puede hacer —y lo que se hizo— es que el número que se muestra esté etiquetado:
el campo del endpoint es `cost_usd_estimado`, la respuesta trae `costo_es_estimado: true`, y la
pantalla lo dice arriba con una nota, no en letra chica. Hay un test que falla si algún campo
aparece nombrado "facturado", que sería mentir.

El costo sale de la tabla de precios de la plataforma (`estimate_cost_usd`), que es lo que
permite frenar por cuota. Para cobrar al centavo hay que cruzarlo con la factura de MiniMax.

## Los fallos también consumen

El acumulado de la cuota cuenta los pedidos `OK` y `ERROR`, no solo los exitosos: si el
proveedor se cae, el costo existe igual y el acumulado tiene que reflejarlo. Los `SIN_CUOTA` y
`SIN_PERMISO` quedan registrados pero no consumen, porque no llegaron a pegarle al proveedor.
La pantalla muestra los dos numeros: `requests` (lo que se cobró) y `registros` (todo lo que
se intentó), y el desglose por operación para poder atribuir un gasto a algo concreto.

## Verificación

- **271 tests del backend** en verde, 15 nuevos, uno por criterio y por camino.
- La aislamiento tiene su propio test: dos empresas con costos distintos, y cada una ve solo
  lo suyo.
- El tablero de plataforma tiene un test que verifica que aparece la empresa **sin** IA
  habilitada pero con consumo, que es la fila que importa.
- Un test del tablero con 403 para un administrador que no es superadmin, y un test de que sin
  `ai.use` tampoco hay consumo que ver.
- 31 del frontend, build OK.

## Pendientes

- #94 (voz e ingesta de documentos) es el único sub-issue que queda abierto de #44. Con este,
  el épico se cierra.
- El tablero muestra **una fila por empresa**, sin drill-down a operaciones por empresa. Si
  aparece una empresa con un gasto raro, hoy hay que ir a la orden o al módulo de la IA a
  buscar qué pasó. Es lo primero que agregaría si el tablero empieza a servir para facturar.
- Sigue en pie que el precio de la plataforma (`ai_price_input_per_million_usd`) es una tabla
  propia. Si el precio real de MiniMax cambia, hay que actualizarla a mano o la cuota va a
  dejar de cortar donde debería.
