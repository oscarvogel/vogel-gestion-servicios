# Bitácora 2026-10-03 (segunda tanda): herramientas de lectura y el modelo que inventa datos

Continúa la tanda de la mañana. Acá arranca el sub-issue 2 de #44 y, sobre todo, el hallazgo
que lo cambió: **en los turnos de seguimiento, el modelo inventa fechas, estados y fallas**.

## Qué se hizo

### Sub-issue 2 de #44: herramientas de solo lectura

Tres herramientas (`buscar_cliente`, `buscar_equipo`, `consultar_historial_equipo`) y el bucle
que las ejecuta. PR #101.

La regla de seguridad es estructural, no una validación: `ToolContext` se arma en el endpoint
con lo que la sesión ya sabe, y la herramienta lo recibe. El modelo elige **qué** llamar y
**con qué argumentos**, nunca a quién le pertenece la información. Un `company_id` en los
argumentos se ignora, y hay un test que lo manda a propósito.

Las pruebas de aislamiento se probaron **saboteando el código**:

| Saboteo | Resultado del test |
|---|---|
| `buscar_cliente` sin filtro de empresa | falla con `{1, 2} == {1}`: se colaba el cliente ajeno |
| `consultar_historial_equipo` sin filtro de empresa | falla con `encontrado is True`: devolvía el historial ajeno |

## El contrato del proveedor, verificado y no supuesto

Contra la API real el 2026-10-03 con `MiniMax-M3`:

- `tools` con la forma de OpenAI: se acepta.
- `finish_reason: "tool_calls"`, y `message.tool_calls[]` con `arguments` como **string JSON**.
- `message.content` puede traer texto además de las llamadas: no implica que no haya nada que
  ejecutar.
- **El rol `tool` sí se acepta** y el round trip funciona. Esto corrigió una afirmación del
  adaptador anterior, que decía que `tool` daba 400. Era falso, y el sub-issue entero depende
  de que fuera cierto.
- `service_tier: "standard"`, que confirma los precios que usa la estimación de costo.

## El bug de fondo: el modelo inventa datos

La pregunta directa funciona perfecto: el modelo encadena `buscar_cliente` → `buscar_equipo` →
`consultar_historial_equipo` y devuelve la realidad.

El problema es el **turno de seguimiento**. Con su propia respuesta anterior en el historial, no
consulta nada y contesta de memoria. Tres corridas, tres historiales distintos, ninguno real:

| Corrida | Lo que respondió | Lo real |
|---|---|---|
| 1 | "15/03/2024, reparación sin iniciar, pantalla sin imagen" | 1 orden |
| 2 | "P001, ENTREGADO, 2026-01-12, pantalla con líneas verticales" | estado "Recibido" |
| 3 | "5 órdenes, la última cambio de display" | 03/10/2026 |

Lo real: 1 orden, estado "Recibido", 03/10/2026, "El cliente trajo la fuente y el cable, no
enciende".

### Las dos palancas del modelo no sirven

Probé las dos contra la API real:

1. **`tool_choice` lo ignora.** Ni `"required"` ni la forma de función forzada: se mandan y el
   modelo responde con texto igual. No se puede obligar a consultar.
2. **El prompt estricto reduce pero no elimina.** Con "respondé solo con lo que te llega de una
   herramienta", una corrida se portó bien y otra inventó un número de orden y una fecha.

Es probabilístico, así que un prompt no es una garantía.

### La solución: que no pueda escribir los datos

PR #102. No se le pide que no invente: se le hace imposible.

- **La ficha la arma el servidor** con los valores de la base. Es la fuente autoritativa.
- **El texto del modelo no puede contener datos**: si tiene un número, una fecha, un id o un
  nombre de estado de la empresa, se descarta entero y queda una frase neutra.
- **`consulto`** viaja en la respuesta, para que el operador distinga una respuesta sin
  consulta de una con ficha.

La regla es verificable: al operador no le puede llegar un dato que no venga de la ficha.

### Tres detalles que costaron encontrar

- **Los estados se comparan sobre el texto entero normalizado.** Palabra por palabra, "está en
  diagnóstico" nunca encuentra el estado "En diagnóstico", que tiene dos palabras.
- **La normalización saca tildes.** El modelo escribe "diagnostico" y la empresa tiene
  "diagnóstico": es el mismo estado.
- **La herramienta repetida se responde con memoria.** El modelo puede pedir la misma
  herramienta con los mismos argumentos varias vueltas. Sin la caché, la ficha se llenaba de
  cuatro copias del mismo bloque; lo mostró el test.

## Verificación

- `pytest`: **173 en verde**.
- Prueba negativa de la garantía: con el saneo desactivado fallan los tests de número, de
  fecha y de estado. Restaurado, los 13 de la respuesta pasan.
- Round trip real contra MiniMax en staging: el modelo encadena las tres herramientas y
  devuelve datos reales (cliente 2041, equipo 4306, serie SN-DOCS, 1 orden en estado
  "Recibido").
- `ai_usage` con atribución por herramienta: `chat`, `chat:peticion_herramientas`,
  `herramienta:buscar_cliente`, `herramienta:buscar_equipo`.

## Pendientes

- **La UI todavía no muestra la ficha.** El backend ya la arma y la manda, pero la pantalla del
  asistente es un sub-issue aparte (#95). Mientras tanto, los datos están en la respuesta de la
  API y el texto va saneado.
- Sub-issue 3 de #44 (#91): herramientas de escritura. Ahora hay un patrón probado para las de
  lectura, y una garantía de que el modelo no puede escribir valores.
- Borrar la empresa de prueba `Prueba Docs` de staging.
- Vincular la API key de WhatsApp con la instancia en la gateway, y cargar `SMTP_*`.
