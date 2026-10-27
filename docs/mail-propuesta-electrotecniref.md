# Mail — propuesta económica para Electrotecniref

- **Para:** admin@electrotecniref.com.ar *(es la dirección que ya usamos con ellos; si preferís otro destinatario, cambiá acá)*
- **De:** Vogel Consultoría
- **Asunto:** Propuesta económica — Vogel Gestión de Servicios para Electrotecniref
- **Adjunto:** `docs/propuesta-abono-mensual-electrotecniref.docx`

---

Hola [nombre / equipo],

Les escribimos con la **propuesta económica** de **Vogel Gestión de Servicios** para
Electrotecniref. Va adjunta (Word, 9 páginas).

La propuesta no es un catálogo: está armada sobre **sus datos reales**. El sistema ya
tiene cargado el histórico completo del sistema anterior —9.316 órdenes de trabajo,
17.565 clientes, 126 áreas— y el cierre a marcas de junio 2025 da 123 trabajos y
$ 1.675.486,90, **idéntico a lo que ustedes tenían**, al centavo. Sobre esa base
definimos qué cubre el abono, con qué límites y con qué compromisos de servicio.

**Lo que propone**

- **Mes 1: ARS 500.000**, en un solo pago, que incluye la puesta en marcha y el primer
  mes de servicio.
- **Desde el mes 2: ARS 300.000 por mes**, con ajuste trimestral por IPC. Sin salto de
  precio por antigüedad.
- **Sin costo por uso**: ni por cantidad de usuarios, ni por orden de trabajo, ni por
  mensaje de WhatsApp.
- **WhatsApp y asistente con IA incluidos.** Los avisos al cliente van sin costo por
  mensaje; si prefieren su propia línea, ponen su propio número y Meta les factura
  directamente a ustedes. El asistente con IA tiene un límite mensual de consumo que
  definimos junto con ustedes.
- **El desarrollo a medida entra en el abono.** No hay cotización por pieza: a medida
  que aparezcan necesidades del taller —una integración, un informe, una marca más— las
  vamos implementando.
- **Catálogo de repuestos contra su ERP**, sin costo adicional: es una integración de
  lectura con el sistema que ustedes ya usan.

La propuesta también detalla los compromisos de servicio (disponibilidad, respuesta
ante incidentes, respaldos, exportación de datos y ventana de mantenimiento) y las
condiciones comerciales.

**Tres definiciones que necesitamos de ustedes**

1. **La lista de precios del catálogo de repuestos**: si vamos con la lista 1 (precio de
   venta con margen) o con la de costo.
2. **El límite de consumo del asistente con IA**, que queda por definir en la puesta en
   marcha.
3. **Si los avisos al cliente salen por la línea de la plataforma o por la línea de
   Electrotecniref.**

**Próximo paso**

Con una reunión de una hora para recorrer la propuesta y cerrar esas tres definiciones
alcanza. La vigencia de la propuesta es hasta el **30 de noviembre de 2026**.

Cualquier duda sobre los números, los límites o el roadmap, la respondemos antes de
firmar.

Quedo a disposición.

[Nombre]
Vogel Consultoría

---

## Notas internas (no van en el mail)

- **Adjunto**: `docs/propuesta-abono-mensual-electrotecniref.docx`, versión del **27 de
  octubre de 2026** (vigencia 30/11/2026). Sale del **PR #130**, que está abierto y sin
  mergear: mandar el `.docx` del branch, no otro.
- **Antes de mandarlo hay que cerrar dos cosas**, porque la propuesta las promete como
  compromiso y el sistema todavía no las tiene:
  - el **respaldo automático diario** (no está configurado en ninguna base) con una
    prueba de restauración real, y
  - la **exportación de datos** en formatos abiertos (hoy no existe; la alternativa es
    el dump de MySQL).
  Está anotado en la bitácora de la propuesta (§5 y §7).
- **La bonificación anual** (12 meses por adelantado, 2 meses sin cargo) está en el
  documento, pero **es una propuesta mía, no un número que haya definido Oscar**. Si no
  va, se saca esa fila antes de mandar.
- **El límite de la IA** quedó en el documento como "a definir en la puesta en marcha",
  a propósito: se define en el paso 2 de la propuesta, con el cliente.
- **Destinatario**: `admin@electrotecniref.com.ar` es la dirección que ya usamos con
  ellos en el mail del staging. Si la propuesta va a una persona concreta o a un
  Mailing de administración, cambiar el encabezado.
- **Firmar** (no mandar ahora): la propuesta promete respaldos y exportación, y los
  pendientes de infraestructura de la bitácora §7 (staging en `main`, histórico en
  producción) son parte de la puesta en marcha.
