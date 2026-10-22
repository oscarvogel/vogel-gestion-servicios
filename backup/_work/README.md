# `_work` — tooling del análisis del backup CiberBrain

Todo lo que hay acá es **herramienta de análisis**, no código de la aplicación.
El resultado del análisis está en [`docs/informe-migracion-ciberbrain.md`](../../docs/informe-migracion-ciberbrain.md).

> **Nada de esto corre contra la base destino.** El `cb-sql` de Docker es una copia
> restaurada del backup legacy y sólo se usa de **solo lectura**.

## Cómo se restauró el backup

```bash
# 1. copiar el .bak al disco nativo de WSL (más rápido que /mnt/c)
cp "/mnt/c/Programacion/vogel-gestion/backup/CB_Miércoles.bak" /home/oscar/cb_restore/cyberbrain.bak

# 2. contenedor SQL Server 2022
docker run -d --name cb-sql -e ACCEPT_EULA=Y -e "SA_PASSWORD=..." \
  -e MSSQL_PID=Developer -e MSSQL_MEMORY_LIMIT_MB=4096 \
  -v /home/oscar/cb_restore:/bak mcr.microsoft.com/mssql/server:2022-latest

# 3. restaurar (ver restore_fix.sh)
RESTORE DATABASE [CiberBase] FROM DISK='/bak/cyberbrain.bak'
WITH MOVE 'CiberBase_Datos'    TO '/var/opt/mssql/data/CiberBase_Datos.mdf',
     MOVE 'CiberBase_Registro' TO '/var/opt/mssql/data/CiberBase_Registro_log.ldf',
     RECOVERY;
```

## Scripts

| Archivo | Qué hace |
|---|---|
| `q.sh` | **Runner de consultas de solo lectura.** `wsl -d Ubuntu -- bash /mnt/c/Programacion/vogel-gestion/backup/_work/q.sh <archivo.sql>` — copia el `.sql` al contenedor y lo corre con `sqlcmd`. **Usá siempre un archivo `.sql`**: el quoting de PowerShell rompe los SQL con comillas simples. |
| `read_header.py` | Lee la cabecera del `.bak` sin restaurarlo (firma, tipo, tamaño). |
| `pipeline.sh` | Espera la imagen, levanta el contenedor y restaura. |
| `restore_fix.sh` | Restaura la base (armando el `MOVE` desde `msdb.dbo.restorefilelist`). |
| `dump_esquema.sh` | Vuelca columnas, PKs, FKs, CHECKs y el catálogo de objetos a `esquema_*.txt`. |
| `dump_filas.sh` | Cuenta filas de las 598 tablas → `filas.txt`. |
| `dump_clave.sh` | Columnas de las tablas clave → `cols_clave.txt`. |
| `dump_procs.sh` | Definición SQL de los procedimientos relevantes → `procs/`. |

## Credenciales

**La password de SA no está en el repo.** Los scripts que hablan con el contenedor la
toman de una variable de entorno:

```bash
export CB_SA_PWD='<password de SA del contenedor cb-sql>'
```

`q.sh` y `export.sh` fallan con un mensaje claro si la variable no está definida.

> Antes de este cambio la password estaba escrita en `q.sh` y `export.sh`. Si alguna vez
> se commiteó, hay que **rotarla** en el contenedor (`ALTER LOGIN sa WITH PASSWORD = ...`)
> y limpiar el historial: una password en el historial de git no se puede "deshacer".

## Exportación a TSV (fase 1 del importador)

`sql/*.sql` + `export.sh` dejan un **snapshot auditable y reejecutable** del corte 2020+
en `csv/*.tsv`. Es lo que después lee `backend/scripts/import_cyberbrain.py`; por eso el
importador no necesita acceso a SQL Server: sólo a los archivos.

```bash
export CB_SA_PWD='<password de SA>'
bash backup/_work/export.sh     # deja backup/_work/csv/*.tsv
```

| Archivo | Filas | Contenido |
|---|---:|---|
| `areas.tsv` | 126 | `Areas` + `TiposTrabajos` (las políticas) |
| `clients.tsv` | 14.730 | `CC_Clientes_Tabla` |
| `work_orders.tsv` | 9.316 | `CS_Trabajos` con `FechaAlta >= 2020-01-01` |
| `parts.tsv` | 29.799 | `CS_Partes` (líneas de los trabajos) |
| `technicians.tsv` | 18.383 | `Intervienen` (quién intervino + comisiones) |
| `part_commissions.tsv` | 10.509 | `CS_ComisionPartexInterviene` |
| `invoices.tsv` | 83.164 | `CG_Facturas_Tabla` |
| `users.tsv` | 44 | `CC_Usuarios` |

**Formato:** separador `|`, **sin encabezado**, y los textos libres vienen sanitizados
desde el SQL (sin CR, sin LF y sin `|`), así que el archivo se parsea con `split('|')`.
Los números y las fechas vienen como texto (`CAST(... AS VARCHAR)`) y los nulos, como
cadena vacía.

`csv/` está en `.gitignore`: son datos regenerables, no código.

## Consultas de perfil y verificación

| Archivo | Qué responde |
|---|---|
| `profile_01.sql` | Rangos de fechas, distribución de estados, unicidad de `NumeroOrden`, calidad de cliente/equipo, duplicados de nombre, CUIT. |
| `profile_02.sql` | Qué hace única a `NumeroOrden` ( Lugar/Año/Sucursal), intervinientes por trabajo, agrupación de equipos, muestra de trabajos. |
| `profile_03.sql` | Trabajos internos, `IDPolitica` vs `Area`, contenido de `Aux_PoliticasxArea`, factura en el trabajo, `CS_UbicacionEquipoLog`. |
| `profile_04.sql` | Trabajos con `CodCli = 0`, columnas de `Aux_PoliticasxArea`, dump de `CC_Usuarios`, `Tipo` de cliente, tabla de contactos. |
| `profile_05.sql` | `TipoTrabajo` de las políticas, distribución de vendedores, roles de `CC_Usuarios`, garantía, ventas por año. |
| `profile_06.sql` | Normalización de categorías de equipo, cobertura de contactos. |
| `profile_07.sql` | Cobertura de teléfonos y contactos. |
| `verify_01.sql` | Conteos de las tablas de ubicación/mesas, distribución de `Garantia`, mesas como texto libre, `TipoDoc` de facturas. |
| `verify_02.sql` | Corte de facturación en 2021-06, facturas por año, qué hay después. |
| `verify_03.sql` | Hipótesis "`Comprobante` es el número de factura post-2021". |
| `verify_com2.sql` | Configuración de comisión por área (`CS_PoliticasxArea`). |
| `verify_com3.sql` | Validación del 50 % sobre `CS_ImporteALiquidarOrden`. |
| `verify_com4.sql` | `CC_ComisionxUsuario`, `CC_PoliticasComisionVendedor`, `CC_EsquemasComision`, quién vende. |
| `verify_com6.sql` | **Validación de la fórmula real** `(venta − costo) × cantidad × %` contra `CS_Partes.CostoComision`. |
| `verify_comisiones.sql` | Esquema de `CS_PoliticasxArea` y `Utilidad`. |

## Artefactos extraídos

| Archivo | Contenido |
|---|---|
| `filas.txt` | 598 líneas: tabla + cantidad de filas. |
| `esquema_cols.txt` | 5.945 líneas: todas las columnas de todas las tablas. |
| `esquema_pk.txt` | PKs e índices únicos. |
| `esquema_fk.txt` | Las **1 sola** FK declarada en toda la base. |
| `esquema_checks.txt` | Los 5 CHECK constraints. |
| `esquema_objetos.txt` | 2.207 objetos (1.193 procedimientos, 387 vistas, 306 funciones, 205 triggers…). |
| `cols_clave.txt` | Columnas de las tablas clave. |
| `procs/` | 69 definiciones SQL volcadas (cálculo de comisiones, liquidaciones, garantía, ubicaciones, facturación). |

## Notas de operación

- **Capacidad del disco**: la imagen de SQL Server 2022 son ~500 MB de capas y el `.bak`
  3,85 GB. La descarga desde MCR en esta máquina va a ~315 KB/s (medido), así que la
  primera vez tarda ~25 minutos.
- **`sqlcmd` 18** no acepta `-i -` (entrada por stdin): hay que copiar el `.sql` al
  contenedor. `q.sh` ya lo hace.
- **Restauración**: el `MOVE` tiene que ir explícito, porque los archivos lógicos se
  llaman `CiberBase_Datos` y `CiberBase_Registro` y sus rutas originales son de otra máquina.
- Para **deshacer** todo: `docker rm -f cb-sql` y borrar `/home/oscar/cb_restore/`.
