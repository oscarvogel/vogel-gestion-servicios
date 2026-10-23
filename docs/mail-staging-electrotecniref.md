# Mail — acceso al staging para Electrotecniref

- **Para:** equipo de Electrotecniref
- **De:** Vogel Consultoría
- **Asunto:** Vogel Gestión de Servicios — acceso al entorno de pruebas con los datos de CiberBrain
- **Adjunto sugerido:** `docs/img/staging-cierre-marcas-junio-2025.png`

---

Hola [nombre / equipo],

Ya está disponible el **entorno de pruebas (staging)** de **Vogel Gestión de Servicios** con los datos
históricos de **CiberBrain** cargados. Lo pusimos online para que lo revisen y empiecen a probarlo con
información real, no con datos de prueba inventados.

**Acceso**

- Dirección: https://gestion-vogel.186.5.245.12.sslip.io/login
- Usuario: admin@electrotecniref.com.ar
- Contraseña: *(se envía aparte; en el repo no queda escrita)*

Al entrar, el sistema los deja directamente en el panel de **Electrotecniref**. Si en algún momento les
pide elegir empresa, elijan "Electrotecniref".

**Qué hay cargados** (el histórico del sistema anterior, de 2001 hasta la fecha del último backup)

| Dato | Cantidad |
|---|---|
| Órdenes de trabajo | 9.316 |
| Clientes | 17.565 |
| Líneas de trabajo (repuestos y servicios) | 29.799 |
| Intervinientes con sus comisiones | 18.383 |
| Facturas | 1.962 |
| Áreas / marcas | 126 |
| Empresas | 3 |
| Usuarios | 52 |

**Qué pueden ver**

- **Dashboard** — el estado de las OTs (abiertas, listas, entregadas), la antigüedad de las abiertas y la
  evolución de las últimas 8 semanas.
- **Órdenes de trabajo** — el listado completo, con búsqueda por cliente, equipo, estado y fechas; y la
  ficha de cada OT con diagnóstico, presupuesto, historial de cambios y archivos adjuntos.
- **Clientes y equipos** — los 17.565 clientes con sus equipos y su documentación.
- **Cierre a marcas** (nuevo) — el cierre mensual por marca, que es la pantalla que hoy más nos importa.
  Junio 2025 da 123 trabajos y $ 1.675.486,90, **idéntico al sistema anterior**. Les dejo una captura abajo.
  Se entra directo por https://gestion-vogel.186.5.245.12.sslip.io/app/cierre-marcas
- **Usuarios, roles y permisos, estados de OT y parámetros** — la configuración de la empresa, para que
  vean cómo quedó organizada.

**Qué les proponemos probar**

- Recorrer el histórico: buscar una OT por cliente o por equipo y seguir su historia completa.
- Cargar una OT de prueba y recorrer el circuito entero: recepción → diagnóstico → presupuesto → ejecución
  → cambio de estado → entrega, y ver cómo queda registrado en el historial de cada OT.
- Generar el cierre de un mes y ver el detalle por empresa (garantía de terceros, garantía propia y fuera
  de garantía).
- Probar la carga de fotos y PDF, tanto en la OT como en la ficha del equipo.
- Probar el listado de clientes: buscar, crear y editar.

**Cuatro cosas a tener en cuenta**

1. Es un **entorno de pruebas**: no afecta a producción. Pero lo que carguen queda acá y se puede borrar
   cuando actualicemos la rama; de eso les avisamos antes.
2. Cuando **emiten** un cierre, ese mes queda **congelado** y los números ya no se recalculan. Si quieren
   volver atrás, avísenme y lo reinicio.
3. El acceso es con un **usuario compartido** de administrador. Si necesitan acceso individual para que
   quede registro de quién hizo qué, les creamos un usuario propio: solo digan a quién.
4. El **Asistente con IA está apagado** por ahora; lo habilitamos cuando corresponda.

**Para el feedback**

Respondan este mail (o escriban a [correo]) con lo que favorece y lo que no. Cada observación entra como
pedido de ajuste en la próxima versión, así que conviene que sea concreto: qué pantalla, qué esperaban y
qué pasó.

Quedo a disposición.

[Nombre]
Vogel Consultoría

---

## Notas internas (no van en el mail)

- Las credenciales están verificadas contra el staging: `admin@electrotecniref.com.ar` /
  la contraseña del usuario de staging entran bien y dejan al usuario en el contexto **Electrotecniref**
  (empresa id=3), sin pedir elegir empresa.
- El menú real de staging (rama `feature/cyberbrain-migracion`) es: Dashboard, Clientes y equipos, Órdenes
  de trabajo, Cierre a marcas, **Técnicos**, Usuarios, Roles y permisos, Parámetros, Estados de OT,
  Asistente y Configuración. **No** incluye "Consumo de IA": esa pantalla es trabajo del otro worker y
  todavía no está commiteada, así que no está desplegada.
- "Técnicos" (maestro y asignación a la OT) entró en la rama el 23/10/2026 y ya está desplegada: el
  mail no la menciona porque para el cliente es parte de la ficha de la OT, no una pantalla nueva.
- El rol Administrador de Electrotecniref tiene permisos de lectura y escritura sobre todo lo del menú
  (incluido `warranty_settlements.manage`), por eso el mail los invita a emitir/cancelar cierres.
- La captura (`docs/img/staging-cierre-marcas-junio-2025.png`) es de la pantalla real, con junio 2025
  cargado y los 15 cierres en estado "Borrador" (ya generados en la sesión anterior).
- Los 46 usuarios importados del legacy (`cyberbrain.N@legacy.invalid`) están en la base pero **no**
  tienen contraseña conocida: por eso el mail da un acceso de administrador y ofrece crear cuentas
  individuales.
- Pendiente de avisar cuando se mergee la rama a `main` y staging vuelva a `main`: el mail dice
  "entorno de pruebas", así que aguanta el cambio sin tener que reescribirlo.
