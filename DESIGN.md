# Vogel · Sistema de diseño

Fuente de verdad visual de Vogel Gestión de Servicios. Los valores viven como tokens en
[frontend/src/styles/tokens.css](frontend/src/styles/tokens.css); las vistas usan los tokens,
nunca el hex directo.

Referencias: `1 · Sistema base oscuro y claro@2x.png` y `Shell + Dashboard@2x.png`.

## Principios

- **Oscuro por defecto, claro alterno.** El botón del topbar nombra el tema al que se pasa
  ("Tema claro" / "Tema oscuro").
- **Plano.** Sin degradados, vidrio ni sombras en tarjetas. La jerarquía sale del color de
  superficie y de un borde de 1 px.
- **El color va en el punto.** Un estado siempre lleva su nombre escrito; el color es un
  punto de 8 px al lado, nunca el único indicador.

## Color

| Token | Uso | Oscuro | Claro |
|---|---|---|---|
| `--color-bg` | Fondo | `#0A1226` | `#F3F5FA` |
| `--color-sidebar` | Menú lateral | `#080F20` | `#FFFFFF` |
| `--color-surface` | Superficie (tarjetas, tablas) | `#101A33` | `#FFFFFF` |
| `--color-chip` | Chip, barra, ítem activo, deshabilitado | `#16224A` | `#EEF1F8` |
| `--color-text-primary` | Texto | `#F3F6FC` | `#0F1F3F` |
| `--color-text-secondary` | Texto 2 | `#B3BDD3` | `#44526F` |
| `--color-text-muted` | Texto 3 | `#8E9AB6` | `#5C6985` |
| `--color-primary` | Primario | `#1F63D6` | `#1F63D6` |
| `--color-link` | Enlaces, número de OT, ítem activo | `#7AA7F7` | `#1F63D6` |
| `--color-danger` | Anular | `#C9353F` | `#C9353F` |
| `--color-border` | Borde de tarjeta y filas | `#1C2848` | `#DDE2EC` |
| `--color-border-strong` | Borde de botón secundario y campo | `#2A3860` | `#C9D0DE` |

### Puntos de estado

`--dot-blue` Recibido / Abiertas · `--dot-teal` Diagnóstico · `--dot-amber` Esperando
aprobación · `--dot-orange` Esperando repuestos · `--dot-purple` En reparación ·
`--dot-green` Completado · `--dot-red` alerta (16 días o más). En claro se usan versiones
más oscuras del mismo tono. Los estados de OT configurados por la empresa traen su propio
color, que se usa como `--dot`.

## Tipografía

| Rol | Estilo |
|---|---|
| Título de pantalla | Inter 28 · 700 |
| Título de sección | Inter 16 · 600 |
| Texto de tabla y formularios | Inter 14 · 400 |
| Encabezado de grupo | Inter 11 · 600, mayúsculas, tracking 0.1em, Texto 3 |
| Códigos (OT 4312) | IBM Plex Mono 13 · 600, color enlace (`.ot-code`) |
| Número de indicador | Inter 36 · 700 |

## Componentes

- **Botones** (`.btn`): radio 10 px, 14 · 600.
  - Primario `.btn--primary`: relleno primario, texto blanco.
  - Secundario `.btn` / `.btn--ghost`: transparente, borde fuerte.
  - Anular `.btn--danger`: relleno rojo, texto blanco.
  - Deshabilitado: relleno chip, Texto 3, sin borde.
- **Campo** (`.field`): etiqueta 13 · 500 en Texto 2 (sin mayúsculas); input con fondo
  `--color-field`, borde fuerte, radio 10 px; foco en primario.
- **Chip de estado** (`.status-chip` + `--dot`): píldora en `--color-chip` con punto de color
  y nombre en texto principal.
- **Tarjeta de indicador** (`.kpi` en el Dashboard): punto + etiqueta en Texto 2, número
  36 · 700, pista en Texto 3.
- **Tabla**: encabezados 11 · 600 mayúsculas en Texto 3, filas separadas por borde, hover
  con `--color-surface-hover`.
- **Barra de progreso**: pista `--color-chip` de 8 px, relleno con el color del tramo.

Radios: `--radius-sm` 6 · `--radius-md` 10 · `--radius-lg` 14 (tarjetas) · `--radius-xl` 18.

## Shell

- **Menú lateral** 256 px, fondo `--color-sidebar`. Arriba el logo oficial de Vogel Consultoría
  (`VogelLogo`), sin cambios. Grupos: Operación (Dashboard, Órdenes de trabajo,
  Clientes y equipos, Técnicos), Finanzas (Cierre a marcas), Asistente IA (Asistente,
  Consumo de IA), Administración (Usuarios, Roles y permisos, Estados de OT, Parámetros,
  Configuración), Plataforma (Empresas). Ítem activo: fondo chip y texto en color enlace.
  Pie: "v0.2 · Modo Empresa".
- **Topbar** 64 px, fondo de página y borde inferior. Izquierda: "Empresa activa" + nombre.
  Derecha: Cambiar empresa, Tema claro/oscuro, nombre + empresa y avatar circular primario.
- **Íconos del menú**: trazo 1,75 px, 24 px, un ícono distinto por pantalla.

## Dashboard

Referencia: `3 · Dashboard de empresa@2x.png`. De arriba hacia abajo:

1. Título "Dashboard", fecha del día de la empresa y botón primario "Nueva orden".
2. **Requieren atención**: cuatro tarjetas-link sobre `--color-bg` (Esperando aprobación,
   Esperando repuestos, Listas para entregar, Más de 15 días) con punto, chevron, número y pista.
   Cada una abre el listado ya filtrado.
3. Cinco indicadores: Abiertas, Ingresadas hoy, Terminadas hoy, Entregadas hoy, Resolución media.
4. **Ingresadas y terminadas por semana** (8 semanas; barras `--chart-received` y `--dot-teal`)
   junto a **Antigüedad** (barras por tramo).
5. **Dónde están las órdenes** (barra apilada + lista con % y cantidad por estado, sin los
   entregados) junto a **Últimas órdenes** (6 filas con OT, cliente/equipo, estado y entrega).

Los encabezados de tarjeta llevan una línea en mayúsculas 11 · 600 (Texto 3) arriba del título.
