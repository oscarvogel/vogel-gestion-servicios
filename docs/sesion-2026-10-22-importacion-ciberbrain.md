# Sesión 22/10/2026 — Importación CiberBrain: el importador contra la base real

Continuación de `docs/sesion-2026-10-22-cierre-marcas.md`. Esta sesión cierra el schema,
comete el trabajo que estaba sin versionar, y corrige el rumbo del importador.

## Qué se hizo

### 1. La rama quedó versionada (4 commits)

`feature/cyberbrain-migracion` estaba con todo el trabajo **sin un solo commit**: dos
migraciones, cinco modelos, el service y la API del cierre, los tests y los dos
documentos de análisis. Eso era el riesgo más urgente de la tarea: una sesión abortada
iba a dejar todo en el working tree.

| Commit | Qué entra |
|---|---|
| `0e703d2` | `docs(ciberbrain)`: informe y plan de la migración |
| `408e7d9` | `feat(migracion)`: schema (migraciones 0024 y 0025, modelos) |
| `bf19fbb` | `feat(cierre)`: cierre mensual a marcas (service, API, permisos, tests) |
| `ddd1ee2` | `chore(backup)`: tooling de análisis del legacy |

Antes de commitear: **289 tests** de la suite completa en verde, más **24** de los nuevos
(`test_cierre_marcas.py` + `test_migrations.py`).

### 2. La password de SA dejó de estar en el repo

`backup/_work/q.sh` y `backup/_work/export.sh` tenían la password de SA escrita en
claro. Como el tooling del legacy se versiona, esa clave iba a entrar al historial de git
— y una password en el historial no se puede "deshacer". Ahora se pasa por
`CB_SQLSERVER_PASSWORD`/`CB_SA_PWD`, con un mensaje claro si falta.

Si alguna vez llegó a commitearse, hay que **rotarla** en el contenedor y limpiar el
historial. Todavía no se hizo: en esta rama nunca se versionaron.

### 3. `backup/` quedó fuera del repo (menos de 4 MB versionados)

El `.bak` pesa 3,67 GB y las exportaciones TSV son datos regenerables: los dos van a
`.gitignore`. Se versiona el tooling (scripts, el volcado del esquema, las 69
definiciones SQL de los procedimientos del legacy, las consultas de perfil y verificación).

### 4. La base real quedó alcanzable desde el venv de Windows

El contenedor `cb-sql` (SQL Server 2022) **no publica puerto**: se levantó sin `-p`, así
que desde Windows no había TCP. Recrearlo habría perdido la base restaurada, que vive en
el volumen del contenedor. La salida fue un **túnel**:

```
Windows localhost:1433 → WSL → cb-tunnel (alpine/socat) → cb-sql:1433
```

- `cb-sql` queda **intacto**, con la base restaurada y `/bak` montado.
- `pymssql` 2.4.5 en el venv del backend, como extra opcional
  (`[project.optional-dependencies] import`), para que el deploy normal no la exija.
- Verificado: `SELECT COUNT(*) FROM CS_Trabajos` → 56.619, `MAX(FechaAlta)` → **2026-10-21**.
  La base está al día; no es un dump vencido.

## El cambio de rumbo

El importador se estaba construyendo contra **`backup/_work/csv/*.tsv`**. Corrección del
usuario: *"lo que hay que importar es la base que está en backup, eso estábamos
trabajando, no el csv. Ciberbrain no csv"*.

Tenía razón, y el plan §4.1 ya lo decía: la opción A (leer la base por TCP con
`pymssql`) era la recomendada y la B (exportar a CSV) era el atajo sin dependencias. El
trabajador se había ido por la B. Corregido: **el importador lee CiberBase**; las
exportaciones TSV quedan como snapshot auditable **contra el cual se cuadra**, no como
fuente.

Lo que sí se conserva del trabajo ya hecho: la arquitectura (pasos, `mappers` con las
reglas de mapeo en un solo lugar, idempotencia por `legacy_id`, modos `--dry-run` y
`--replace`, y el reporte de cuadre). Solo cambia la capa de lectura.

## Bugs y bloqueos encontrados, y cómo se resolvieron

### La garantía no es un campo, son tres tablas encajadas

`Areas` + `TiposTrabajos` + `Aux_PoliticasxArea`. `CS_Trabajos.Garantia` es el flag de
la OT, no el de la política, y difieren. La fuente correcta es la **vista**
`CS_PoliticasxArea`, que ya resuelve `Garantia` y `Liquidar` con la regla real del legacy
(principal vs sub-tipo). Por eso `work_areas` guarda las dos capas: `area_code` +
`policy_code`, con la garantía ya resuelta en `warranty_type`.

### "Liquidar" no es "a quién se liquida"

Es el ciclo de vida de la OT (0 y 3 = liquidación manual, 1 = automática, 2 = nunca),
según `proc_CS_EstadoPosible`. Si el cierre filtrara por ese flag, excluiría **justo la
garantía**, que es lo que hay que liquidar. "A quién se liquida" es exclusivamente
`Areas.CodCli` — y ese campo está desactualizado en el legacy (el área 14 dice ARISTON
pero factura a INDESIT).

### El legacy no tiene nada de cierre a marcas

No hay importe liquidado a la marca, así que **no hay contra qué validar el primer
cierre**: hay que compararlo contra una consulta equivalente escrita a mano
(`backup/_work/ver_cierre.sql`) y contra la salida del importador.

### `NumeroOrden` no sirve como número de OT

12.886 números para 56.619 OTs, con hasta 60 repeticiones y el 69 % vacío. El número de
OT del sistema nuevo es propio y correlativo; el original queda en `legacy_number`.

### El 64 % de las OTs del corte no tiene cliente

**5.969 de 9.316** tienen `CodCli = 0`, y `work_orders.customer_id` es NOT NULL. Pero la
OT trae el cliente copiado (`Cliente`, `NroDocumento`, `Telefonos`, `EMail`, dirección):
de esas 5.969, **ninguna tiene el nombre vacío**, y hay 3.593 nombres distintos. Se
crean los clientes desde el snapshot de la OT, agrupados por nombre normalizado. Así no
se descarta ninguna OT.

### El documento del cliente no existe como dato confiable

De 14.730 clientes, **sólo 197** tienen CUIT válido (se deriva de las facturas: el CUIT
más frecuente por cliente). Hay además **13 CUITs repetidos entre clientes distintos**,
que romperían el unique `(company_id, document)`. Y el `NroDocumento` de la OT no sirve:
de 1.360 documentos distintos, 1.308 tienen 10 caracteres, y hay longitudes de 6 a 17.

Regla: `document` se puebla **sólo** con CUIT de 11 dígitos **único**; los 13 duplicados
pierden el CUIT (el primero lo conserva) y quedan reportados. El resto, NULL. *Si el
documento no sirve para identificar, que no identifique: es preferible un NULL honesto a
un dato falso.*

### No hay maestro de equipos

`DatosEquipos` tiene exactamente 56.619 filas: una por OT. Es otro snapshot, no un
maestro. Y las series no sirven para deduplicar: 441 `ILEGIBLE`, 211 `S/N`, 19 `FALTA`
(el 87 %), más 92 pares (equipo+serie) que comparten clientes distintos. Entonces **un
`equipment` por OT**, tomado de `CS_Trabajos.Equipo/Modelo/NroSerie`. Deduplicar por
serie sería inventar datos que el legacy no tiene.

### `customers.document` y `work_orders.customer_id`: el `unique` y el `NOT NULL`

Los dos `NOT NULL` del destino (`customer_id`, `equipment_id`) condicionan el mapeo
completo, y `received_by_user_id` obliga a mapear el `Usuario` de la OT contra los 44
usuarios del legacy.

## Estado de las cifras (medidas contra CiberBase, 22/10/2026)

| Tabla / conjunto | Filas |
|---|---:|
| `CS_Trabajos` (todas) | 56.619 |
| `CS_Trabajos` desde 2020-01-01 | **9.316** |
| `CC_Clientes_Tabla` | 14.730 |
| `CS_Partes` del corte | 29.799 |
| `Intervienen` del corte | 18.383 |
| `CS_ComisionPartexInterviene` | 10.509 |
| `CG_Facturas_Tabla` | 83.164 |
| `CS_PoliticasxArea` (políticas) | 126 |
| `CC_Usuarios` | 44 |

Costo del corte 2020+: **101.374.150,50**. Por estado: 8 = 8.506 OTs (93.673.309,15),
7 = 646 (7.509.948,78), 4 = 42 (190.892,57), 6 = 70, resto 52.

Cierre mensual (criterio implementado): **6.418 OTs / 73,2 M** con empresa a liquidar, de
las cuales **2.853 / 25,4 M** son garantía estricta y **3.565 / 47,8 M** son trabajo fuera
de garantía que las marcas igual pagan.

## Cómo se ejecuta la importación

1. **Origen**: CiberBase por `pymssql` a `localhost:1433`, en lotes de 1.000 con
   `fetchmany`, leyendo con los SQL de `backup/_work/sql/*.sql` (ya validados contra la
   base restaurada).
2. **Destino**: MySQL 8.4 del contenedor `vogel-mysql` en `localhost:3307`, base
   `vogel_gestion_servicios`, schema en `alembic_version = 20261022_0025`.
3. **Orden por FK**: empresa → usuarios/sellers/technicians/mesas → `work_areas` →
   `customers` → `equipment` → `work_orders` → `work_order_parts` →
   `work_order_technicians` → `work_order_part_commissions` → `invoices`.
4. **Primero `--dry-run`**: valida y cuenta sin escribir. Después, la corrida real.
5. **Idempotente**: `legacy_id` + unique. Se puede re-ejecutar sin duplicar, y
   `--replace` rehace un paso.
6. **Cuadre**: contra el legacy con `backup/_work/ver_cierre.sql` y contra el snapshot
   TSV. Si el cuadre da distinto, **el legacy manda**.
7. **Nada de esto toca staging ni producción**: el MySQL local de WSL es el banco de
   pruebas.

## Pendientes

- [ ] **Importador**: terminar de cambiar la capa de lectura a `pymssql` y correr el
      `--dry-run` completo.
- [ ] **CUIT de la empresa**: no es derivable del legacy. El CUIT que más factura es
      `20111111112`, que es un placeholder. Hay que cargarlo a mano para crear
      "Electrotecniref".
- [ ] **Alcance del cierre (§9.1)**: sigue abierta la decisión entre A (sólo garantía
      estricta: 2.853 OTs / 25,4 M) y B (todo lo que tiene empresa a liquidar:
      6.418 OTs / 73,2 M). El código implementa **B**; hay que confirmarlo.
- [ ] **Alladio (§9.2)**: ¿marca de fábrica o service oficial? Define si sus OTs
      entran al cierre y contra quién se liquida.
- [ ] **Persona vs empresa y mesas (§9.3, §9.4)**: hay default asumido y anotado
      (persona jurídica y "múltiples"), no bloquean.
- [ ] **Validación de CUIT contra AFIP**: pendiente, no bloquea la importación.
- [ ] **Pantalla del cierre**: no existe en el frontend. Hay backend y API, no UI.
- [ ] **Prueba contra junio 2025** (el mes ya medido: 91 OTs en garantía /
      1.045.148,15) antes de cargar el corte completo.
