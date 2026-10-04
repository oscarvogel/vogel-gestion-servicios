# Bitácora 2026-10-04: presupuestos con IA desde datos reales (#44, sub-issue 4)

Cierra el sub-issue 4 de #44. Es el primero que pone plata en el medio, y por eso es el
primero donde "la IA no puede inventar precios" deja de ser una frase y pasa a ser una
propiedad que un test verifica.

## Las dos herramientas

- **`calcular_presupuesto`** (lectura, `work_orders.view`) — arma el presupuesto de la orden
  con los trabajos y repuestos que ya tiene cargados, y dice qué le falta. No escribe nada.
- **`generar_presupuesto`** (escritura, `work_orders.manage`) — deja la propuesta pendiente
  para que una persona la confirme, como las otras seis herramientas de escritura.

## La decisión que sostiene el sub-issue

**`generar_presupuesto` no tiene ningún campo de precio.** No es que lo valide, es que no
existe. Los argumentos son `orden` y `notas`, y las líneas se derivan del lado del servidor.

Si la herramienta aceptara importes, el modelo podría mandar un precio y quedaría igual de
creíble que uno real: la única defensa sería pedirle a la persona que lo revisara, y una
revisión humana **no detecta un número inventado, solo uno raro**. Un operador mirando
"$18.500" no tiene forma de saber si viene de la lista de precios o del dedo del modelo.
Sin campo, no hay por dónde inventarlo.

Esto también resolvió un problema de la pantalla de confirmación: los argumentos se editan
como campos de texto plano, así que una lista de ítems se habría renderizado como
`[object Object]`. Al no haber ítems entre los argumentos, el diálogo existente funciona sin
cambios.

Hay un test que fija esto estructuralmente, mirando el `ToolSpec`:

```python
def test_generar_presupuesto_no_tiene_ningun_parametro_de_importe():
    herramienta = next(t for t in TOOLS_ESCRITURA if t.name == "generar_presupuesto")
    propiedades = set(herramienta.parameters.get("properties", {}))
    assert propiedades == {"orden", "notas"}
```

Si alguien agrega un `precio_unitario` o un `items` a esa herramienta, el test revienta. Es la
red que hace que la regla no dependa de que alguien se acuerde de ella.

## La trazabilidad

Cada línea del cálculo trae `origen_id`, que es el id del trabajo o repuesto del que salió, y
`origen_del_precio`, que dice de dónde salió el número:

| `origen_del_precio` | Qué significa |
|---|---|
| `precio_cargado` | alguien cargó el precio en la línea de la orden |
| `costo_mas_markup` | no había precio, sale del costo con el margen de la empresa |
| `sin_precio` | no hay dato, y la línea queda `pendiente` |

Con `sin_precio`, `precio_unitario` viene en `null`, la línea no suma al total y la razón
aparece en `pendientes`. Y `generar_presupuesto` **falla** con esa lista, sin dejar
propuesta. No es "proponer con lo que hay": es no proponer y explicar.

## `show_internal_costs` respetado de verdad

Con la empresa en `show_internal_costs = false`, el cálculo no devuelve `costo_unitario`, ni
`markup`, ni `margen`.

Lo importante es una cosa menos obvia: **el costo tampoco habilita el precio**. Si la línea
tiene costo 10.000 y no tiene precio, con costos visibles el precio sale 15.000 con el
margen del 50%. Con costos ocultos la línea queda pendiente. Porque si el modelo ve 15.000 y
sabe que el margen es 50%, ya sabe que el costo era 10.000: derivar el precio de un costo
oculto es filtrar el costo por la puerta de atrás.

## Lo que la IA avisa sin bloquear

La mano de obra no lleva markup —el parámetro es `pricing.parts_markup_percent`—. Entonces
cuando el precio de una línea de trabajo sale del costo, el resultado es el costo mismo. El
número sale de un dato real, así que no se bloquea, pero ofrecerle al cliente el costo como
precio deja margen cero. Eso va a `avisos`, que es una lista distinta de `pendientes`: una
dice "esto no se puede", la otra dice "esto se puede, pero miralo".

## Un camino, no dos

La creación de presupuestos vivía entera dentro del handler `POST /work-orders/{oid}/quotes`:
el versionado, el markup, el redondeo, el cierre del diagnóstico y el movimiento de estado.
Para que la IA no aplicara reglas distintas a las de la pantalla, esa lógica se extrajo a
`app/services/work_orders.py` (`crear_presupuesto`) y el handler ahora delega. Lo mismo con
`parameter_bool`, `markup` y `money`, que ahora tienen una sola definición.

Esto es lo que el docstring de ese servicio ya decía desde el sub-issue 3: *"la API y las
propuestas de la IA tienen que escribir por el mismo camino"*. Con los presupuestos ya no es
una intención, es que las dos cosas llaman a la misma función.

Un test mide que las dos den el mismo número, para que la delegación no se rompa en el futuro.

## Un bug que encontré y no buscaba

`agregar_trabajo` (sub-issue 3) guardaba `item_type = "WORK"`. El dominio entero habla `PART`
y `LABOR`: la API valida `^(PART|LABOR)$`, la pantalla separa con `item_type === "PART"`, y las
columnas del presupuesto son `subtotal_parts` y `subtotal_labor`.

No se veía roto porque la pantalla cae en la rama "no es PART" y lo muestra como Trabajo, que
era justo como se debería ver. **Se veía al usar el dato**: el cálculo del presupuesto
distingue repuesto de mano de obra para aplicar el margen solo a los repuestos. Con `WORK`,
dependía de que el que escribiera la fila se acordara de la convención.

Corregido en el aplicador, y migración `20261004_0022` para las filas ya escritas. La
migración es idempotente y su `downgrade` está documentado como no exacto: bajarla mezcla
las filas viejas con las nuevas, porque después de la corrección la herramienta ya escribe
`LABOR`.

## Verificación

- **24 tests nuevos** en `tests/test_ai_presupuestos.py`, uno por criterio del issue.
- El test del vocabulario `LABOR` se validó **contra el código roto**: se revirtió el fix y
  falla con `assert 'WORK' == 'LABOR'`. Un test que pasa contra el código roto no prueba
  nada.
- El test de la migración se validó contra el estado previo que sembró él mismo: antes hay
  `['PART', 'WORK', 'WORK']`, después `['LABOR', 'LABOR', 'PART']`.

## Dos cosas que encontré y no toqué

1. **Emitir un presupuesto mueve la orden a "Presupuestado" sin pasar por `cambiar_estado`,
   y por lo tanto no encola el aviso del cliente**, aunque ese estado tenga WhatsApp
   configurado. La pantalla tiene ese comportamiento desde siempre, así que la IA lo heredó
   en vez de inventar uno. Corregirlo haría que a los operadores de a pie les empiece a
   llegar un WhatsApp que hoy no llega: es una decisión de producto, no un bug que deba
   arreglar de paso. Queda anotado acá.

2. **`datetime.utcnow()` está en `proposals.py` y `work_orders.py`**, y Python ya lo marca
   como deprecado. No es un problema hoy, pero tiene fecha de vencimiento.

## Pendientes

- Verificar en el navegador que el diálogo de confirmación de `generar_presupuesto` se ve
  bien y que la vista previa con los importes le llega al operador antes de confirmar. Los
  tests cubren el backend; la pantalla no se abrió todavía.
- La lista de clientes de prueba en staging sigue pendiente de borrar a mano: 2042, 2043 y
  2044 (viene del sub-issue 7).
- Sub-issues de #44 que siguen abiertos: #93 comunicación, #94 voz, #96 métricas.
