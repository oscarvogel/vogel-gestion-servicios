# Bitácora 2026-10-04: preparar comunicación con el cliente (#44, sub-issue 5)

Cierra el sub-issue 5 de #44. Es el primero que escribe algo dirigido a una persona que no es
del equipo, y eso cambia la pregunta: en el sub-issue 4 el error era un número feo, acá el
error es un WhatsApp que salió y no se puede deshacer.

## La decisión que sostiene el sub-issue

**`preparar_comunicacion_cliente` no envía.** Encola el aviso en `PENDING`, con su evento, y
devuelve. El envío lo hace una persona desde la orden.

El mecanismo es concreto y no es una convención: `_aplicar` devuelve `(referencia, notificado)`,
`confirmar` lo guarda en `propuesta.notified`, y `_despachar` en el endpoint solo despacha si
ese flag es True. La herramienta propone con `notifica=False`, y su aplicador devuelve `False`.
Confirmar prepara. Si devolviera `True`, confirmar sería enviar, que es justo lo contrario de lo
que pide el issue.

Y eso se verificó contra el código roto, no de palabra: con el aplicador devuelve `True`, el test
que va por el endpoint falla con `{'sent': 1}` — el mensaje salió de verdad. Ese es el síntoma
que el sub-issue prohíbe.

## Un hueco que apareció al implementarlo

Los avisos se mandan solos cuando cambia el estado de la orden. **No había ninguna forma de
mandar a mano uno que quedara pendiente.** Los tres caminos de despacho que existían eran: el
cambio de estado, la confirmación de una propuesta con `notified`, y un drenador
(`dispatch_pending`) que no lo llama nada en el repo.

O sea: "deja el aviso listo para que la persona lo envíe" sin ninguna parte de "y lo envíe"
era un callejón sin salida. Así que el sub-issue incluye el botón de enviar, porque sin él la
herramienta no cumple lo que promete.

Lo que se agregó: `POST /work-orders/{id}/notifications/{notification_id}/send`, con las
protecciones que corresponden — no se puede mandar dos veces el mismo aviso (409, para que un
doble clic no duplique el mensaje al cliente) y uno `SKIPPED` no es reintentable, porque sin
destinatario no hay nada que reintentar. Y en la fila del aviso, un botón para **leer el
mensaje** antes de mandarlo: mandar sin leer sería mandar a ciegas.

## Reutiliza #45, no un camino nuevo

El texto sale de `plan_for_event`, la misma función que usa el modal de confirmacion de la
pantalla. Si la herramienta calculara el mensaje por su cuenta, tarde o temprano divergiría de
lo que se manda, y un cliente que recibió otra cosa es el peor resultado posible.

Cada aviso cuelga de un **evento propio** de tipo `NOTICE`, no del evento de cambio de estado.
Eso no es folclore: el outbox tiene un unique `(company_id, work_order_event_id, channel)`, así
que colgar el aviso de un cambio de estado haría chocar contra la base en cuanto la orden
cambiara de estado otra vez. Hay un test que prepara dos avisos seguidos y verifica que no
chocan.

## Lo que el modelo puede y lo que no

Puede escribir el texto (`mensaje`) y elegir el canal (`canal`). No puede elegir destinatario.
Si el cliente no tiene número, la herramienta **falla diciendo que no hay a quién mandarle**, en
lugar de dejar un aviso `SKIPPED` que la persona tiene que interpretar sola. Un canal
inventado se rechaza antes de proponer nada.

El texto del modelo va en el diálogo de confirmación, editable, y lo que se guarda es lo
corregido: hay un test que manda un mensaje con un error, lo corrige al confirmar y verifica
que la corrección es lo que quedó escrito.

## Verificación en pantalla, otra vez

Igual que en el sub-issue 4, los tests no miran la pantalla. Y acá importaba más, porque lo que
se ve antes de confirmar es un mensaje a un cliente.

Por eso el diálogo pide `POST /work-orders/{id}/communication-preview` al abrirse y muestra, en
un bloque antes de los campos: canal, destinatario y **el texto con las variables ya
resueltas**. Sin eso, la persona confirmaba viendo el `{{cliente}}` sin resolver y sin saber a
qué número iba a llegar. Un mensaje de WhatsApp con dos saltos de línea encima pasó a ser un
`<textarea>` de ancho completo, porque en un `<input>` de una línea es ilegible.

El bloque lleva una aclaración explícita en amarillo: "Confirmar lo deja **pendiente** en la
orden. No se envía solo: lo mandás vos." Sin esa frase, un botón que dice "Confirmar y aplicar"
al lado de un WhatsApp se lee como "se manda ahora", que es la confusión que este sub-issue
existe para evitar.

## Un test que no sé si sobra

`toda_herramienta_de_escritura_tiene_su_aplicador` recorre el catálogo y verifica que ninguna
herramienta quede sin su entrada en `APLICADORES`. Una herramienta sin aplicador se propone,
se confirma, y falla recién en producción, con el mensaje "no hay función para aplicar X" en
lugar de algo útil. Cuesta cuatro líneas.

## Verificación

- **22 tests nuevos** en `tests/test_ai_comunicacion.py`, uno por criterio del issue más los que
  hacen de red: que preparar no manda, que el aviso es auditable, que es de otra empresa no se
  lee ni se manda, que no se puede mandar dos veces.
- El test de "no manda" se validó **contra el código roto** en los dos niveles: con el aplicador
  en `True` fallan tanto el test de `confirmar` como el que va por el endpoint, y este último
  con el síntoma real, `{'sent': 1}`.
- Los 218 tests anteriores del backend siguen en verde.

## Pendientes

- Verificar en el navegador el diálogo de la comunicación y el botón de enviar. Los tests
  cubren el backend y la vista previa se pide por el mismo endpoint que testea el backend, pero
  **la pantalla no se abrió todavía** para este sub-issue.
- Sigue abierta la decisión de si emitir un presupuesto debe avisar al cliente (quedó anotada
  en el sub-issue 4). Ahora hay un botón de enviar a mano, así que hoy el camino es: preparar,
  que alguien lo mande. Cambiar el comportamiento del presupuesto es otra decisión, y ahora es
  más fácil de cambiar: basta con que `crear_presupuesto` encole el aviso.
- La lista de clientes de prueba en staging sigue pendiente de borrar a mano: 2042, 2043 y
  2044.
- Sub-issues de #44 que siguen abiertos: #94 voz, #96 métricas.
