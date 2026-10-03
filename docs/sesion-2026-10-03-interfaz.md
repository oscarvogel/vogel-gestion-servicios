# Bitácora 2026-10-03 (cuarta tanda): interfaz del asistente

Cierra el sub-issue 7 de #44. Es la pieza que hacia falta: el backend de los tres sub-issues
anteriores estaba completo y desplegado, pero **no habia nada en el frontend que lo
consumiera**. Desplegar `main` mostraba la aplicacion exactamente igual que antes, y esa era
la pregunta con la que arranco esta tanda.

## Que hace la pantalla

Ruta `/app/assistant`, visible solo con el permiso `ai.use`. Conversacion, ficha de datos,
propuestas pendientes y el dialogo de confirmacion.

### Los tres criterios del issue

**Nunca se ve una accion a punto de ejecutarse sin haberla confirmada.** El modelo no ejecuta
nada: deja una propuesta, y la unica forma de aplicarla es el dialogo, con un boton que dice
"Confirmar y aplicar". No hay ningun camino donde apretar "Enviar" aplique algo.

**El panel dice por que la IA no esta**, distinguiendo los cuatro motivos que el backend ya
separa: no contratada, credencial no cargada, proveedor caido, cuota agotada. La caida se
muestra como "podes seguir trabajando normalmente", porque la pantalla es un adicional y no
una dependencia del sistema.

**La interfaz se opera completa sin IA.** El enlace no existe sin el permiso, la ruta responde
403, y el resto de la aplicacion no cambia.

### La ficha va antes del texto del modelo

El backend descarta el texto del modelo cuando trae numeros o estados, y manda los datos
aparte en `ficha`. Por eso la interfaz los muestra en ese orden: **la ficha es la fuente y el
texto es un comentario**. Al reves, el comentario pasaria por el dato.

Ademas, cuando se pidieron herramientas y el modelo no consulto ninguna, la burbuja lo avisa.
Sin ese aviso, una respuesta sin consulta se ve igual que una que si consulto.

### El dialogo de confirmacion

Dice **que va a pasar** en castellano, deja **editar** los valores, marca el **riesgo antes** de
dejar confirmar, y al cambiar de propuesta borra la edicion anterior para que no quede el valor
de la previa pegado.

## Verificacion

- `npm run build`: compila.
- `vitest`: **31 en verde** (18 previos + 13 nuevos).
- La garantia central probada **saboteando el codigo**: agregarle al `enviar()` una linea que
  confirme la primera propuesta pendiente hace fallar
  `una propuesta pendiente aparece y NO se aplica al mandar un mensaje`.

## Un bug que solo aparecio con un test

`filias` en vez de `filas` en la plantilla de la ficha. No lo detectaba ningun test anterior
porque la otra prueba usaba una ficha **vacia**, que nunca entra a esa rama: el error
aparecia como "la burbuja del asistente queda en blanco", sin mensaje.

Eso es lo que mas cuesta ver en un componente con ramas: un test que solo recorre un camino
no encuentra los errores del otro, y el sintoma aparece lejos de la causa.

## Verificacion en el navegador, y un bug que solo se ve ahi

Probado en Chrome contra staging, con la empresa `Prueba Docs`:

- El enlace "Asistente" aparece en el menu, la ruta responde y la pantalla carga.
- Consulta de datos: el modelo encadena ``buscar_equipo`` y ``consultar_historial_equipo``, y la
  ficha muestra equipo 4306, Samsung QLED, serie SN-DOCS, 1 orden en estado "Recibido" del
  3/10/26, con la falla real. **La ficha queda arriba y el texto del modelo abajo.**
- Alta de cliente: el modelo propone "PRUEBA NAVEGADOR SIN CORREGIR", **la API confirma que
  no se escribio nada** (0 clientes), aparece "ACCIONES ESPERANDO TU CONFIRMACION 1" con
  "Nada de esto se aplico todavia", y los unicos botones son Descartar y Revisar.
- El dialogo abre con los campos editables; se corrigio el nombre a "PRUEBA NAVEGADOR
  CONFIRMADO" y al confirmar: cliente 2044 con el nombre **corregido**, 0 con el nombre sin
  corregir, y ``lo_que_cambio`` con la correccion registrada.

### El bug de layout

La tabla del historial tiene cinco columnas y no entra en una pantalla angosta. Se desbordaba y
**"Falla reportada" quedaba cortada**, que es justo el dato que el operador necesita leer. Se
vio recien en la captura del navegador: ningun test lo detecta, porque el CSS no se prueba.

El arreglo son dos lineas (`min-width: 0` y `overflow-x: auto`), y el `min-width` es la parte
importante: un contenedor flex sin eso no baja del ancho de su contenido, asi que el `overflow`
solo no habria hecho nada. PR #107.

## Dos cosas que decia mal el codigo y corrects

- El icono del menu no cerraba el ``<script setup>``: no compilaba. Lo agarro ``npm run build``,
  no un test.
- En la ficha, la funcion se llamaba ``filas`` y la plantilla pedia ``filias``. No lo detectaba
  ningun test anterior porque la otra prueba usaba una ficha **vacia**, que nunca entra a esa
  rama. Sintoma: la burbuja del asistente en blanco, sin error visible.

## Pendientes

- Quedan clientes de prueba en staging para borrar a mano: 2042, 2043 y 2044.
- Sub-issues de #44 que siguen abiertos: #92 presupuestos, #93 comunicacion, #94 voz,
  #96 metricas.
