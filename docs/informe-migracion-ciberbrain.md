# Informe: migración CiberBrain (CiberBase) → Vogel Gestión de Servicios

> **Estado:** informe de análisis. **No se modificó código de la aplicación.**
> Fecha: 2026-10-22. Todos los números salen de consultas SQL sobre la base legacy
> restaurada, no de la lectura del código.

---

## 0. Resumen ejecutivo

El backup `CB_Miércoles.bak` es un **backup nativo de SQL Server** de la base **`CiberBase`**
— el ERP de service de **ELECTROTECNIREF**. Se restauró y quedó consultable: la base está
**viva y actualizada hasta el mismo día del dump (2026-10-21)**, no es un archivo vencido.

**Lo que hay adentro:** 598 tablas (320 con datos), 2.207 objetos de programación,
56.619 órdenes de trabajo entre 2001 y 2026, 14.730 clientes, 83.154 asignaciones de
técnicos y 83.164 facturas.

**Se puede migrar clientes, equipos y tareas realizadas.** Los datos modernos (2020+) son
de alta calidad: 99 % de las OTs tiene técnico asignado, 98,8 % tiene el trabajo
realizado y 98,4 % tiene fecha de listo.

**Los cinco bloqueos reales para la migración:**

1. **`NumeroOrden` no es único** (56.619 OTs → 12.886 números distintos) y el 69 % está
   vacío ⇒ el correlativo del sistema nuevo tiene que ser propio, no heredado.
2. **El documento del cliente no existe en la tabla de clientes** (sólo 3.151 de 14.730 lo
   tienen, y en `CG_Facturas_Tabla`, con valores placeholder) ⇒ el unique
   `(company_id, document)` del destino no se puede poblar con el CUIT legacy.
3. **El 16 % de las OTs (9.151) no tiene cliente vinculado** (`CodCli = 0`), aunque el
   nombre del cliente suele estar copiado en la propia OT ⇒ recuperables por emparejamiento.
4. **La garantía no está en el campo `Garantia`**: se resuelve por la **política**
   (`IDPolitica` → área × tipo de trabajo) y por una **jerarquía de plazos**.
5. **La factura cambió de campo a mitad de vida**: hasta 2021 en `FacturaEmitida`, después
   en `Comprobante` (que además es polimórfico: número de factura *o* texto de estado).

**Y el hallazgo de fondo:** el legacy **no tiene maestro de mesas de trabajo**
(`UBIC_Ubicaciones`, `CS_Ubicaciones` y `CK_Ubicaciones` están **vacías**) y las mesas se
cargan como **texto libre** en `CS_Trabajos.Ubicacion` (`TALLER`, `TALLER-BOX1`,
`TALLER - BOX A`…). El sistema nuevo tiene que decidir si crea ese maestro o sigue igual.

### Respuesta corta a los seis temas pedidos

| Tema | Respuesta |
|---|---|
| **Comisiones de vendedores** | Hay **dos motores distintos**. La del **vendedor** se recalcula al vuelo sobre las facturas (`CC_ComisionesVentas`) y **no se persiste**; la del **técnico** sí se persiste (`Intervienen.Comision*`). El interruptor real es `CS_Partes.LiquidaComision`, y el porcentaje sale de la **política del área** (50 % de utilidad sobre el servicio). Tres políticas deciden a quién se le acredita: vendedor del comprobante, del cliente, o ambos. |
| **Garantía / fuera de garantía** | `Garantia` es un tinyint de 3 estados (0 / 1 / 2) y `TipoTrabajo = 'FUERA'` en la política marca las 55 áreas fuera de garantía. El **plazo** sale de una jerarquía (producto → artículo → agrupación → política) y el vencimiento es `DATEDIFF(mm, FechaComprobante, Fecha) > DuracionGarantia`. |
| **Empresa** | **En el legacy no existe el campo.** `Tipo` es el canal comercial ("GREMIO MAYORISTAS"), no persona/empresa. Hay que derivarlo del CUIT (validado) y del sufijo societario del nombre. 288 nombres repetidos (una fila por sucursal de la misma empresa). |
| **Técnicos** | No son una tabla: son `CC_Usuarios` con la tarea 3 (`CC_Tareas`). 11 técnicos activos, y **40 de las 77 personas que intervinieron ya no existen** (32.798 filas de `Intervienen` sin nombre ⇒ el legacy muestra "Sistema"). |
| **Fecha y número de factura** | `CG_Facturas_Tabla.Numero` = `A0004-00002010` (grupo + punto de venta + talonario, **sin reinicio anual**); la clave es `(TipoDoc, Numero)`; la fecha es `Fecha`. **Pero desde 2021 las OTs ya no la linkean**: el número quedó en `CS_Trabajos.Comprobante`, un campo **polimórfico** (4.699 números de factura + textos como `STOCK`, `FALTA FACTURA`). |
| **Mesas de trabajo** | **Texto libre**: `CS_Trabajos.Ubicacion` (`TALLER`, `TALLER-BOX1`…). Las 4 tablas candidatas a maestro están **vacías**. `CS_TipoUbicaciones` no son mesas sino "dónde está el equipo" (Domicilio / Taller propio / Taller responsable / Comercio / Terceros). El histórico es `CS_UbicacionEquipoLog` (92.394 filas). |

---

## 1. Qué es el backup y cómo se lo abrió

| Dato | Valor |
|---|---|
| Archivo | `backup/CB_Miércoles.bak` |
| Tamaño | 3.852.582.912 bytes (3,85 GB) |
| Formato | Backup nativo de **Microsoft SQL Server** (firma `TAPE` / `SPAD` en la cabecera) |
| Base | **CiberBase** |
| Tipo | Completo (`BackupType = 1`), comprimido |
| Páginas | 470.178 (3,97 s, 925 MB/s) |
| Inicio / fin del backup | **2026-10-21 13:30:00** / 13:30:30 |
| Collation | `Modern_Spanish_CI_AI` |
| Archivos lógicos | `CiberBase_Datos` (MDF, PRIMARY, 3.996.647.424 bytes), `CiberBase_Registro` (LDF) |
| Rutas originales | `C:\Datos\Bases de Datos\Ciberbase_datos.MDF` |

Restaurado en un **contenedor Docker con SQL Server 2022** dentro de WSL (`cb-sql`),
quedó `ONLINE`. La base original es de **ELECTROTECNIREF** (los usuarios del legacy
tienen correo `@electrotecniref.com.ar`).

> La cabecera declara `DatabaseCreationDate = 2019-06-19`: en 2019 se restauró un backup
> sobre la instancia y **el sistema siguió acumulando datos desde ahí**. Los datos llegan
> **hasta el día del dump**.

### Cómo reproducirlo

```bash
# WSL: contenedor SQL Server 2022
docker run -d --name cb-sql -e ACCEPT_EULA=Y -e "SA_PASSWORD=..." \
  -e MSSQL_PID=Developer -e MSSQL_MEMORY_LIMIT_MB=4096 \
  -v /home/oscar/cb_restore:/bak mcr.microsoft.com/mssql/server:2022-latest

# restauración
RESTORE DATABASE [CiberBase] FROM DISK='/bak/cyberbrain.bak'
WITH MOVE 'CiberBase_Datos'    TO '/var/opt/mssql/data/CiberBase_Datos.mdf',
     MOVE 'CiberBase_Registro' TO '/var/opt/mssql/data/CiberBase_Registro_log.ldf',
     RECOVERY;
```

Scripts reutilizables en `backup/_work/` (con su propio README):
`q.sh` (consulta de solo lectura), `pipeline.sh`, `restore_fix.sh`, `dump_esquema.sh`,
`dump_procs.sh`, `dump_clave.sh`, `dump_filas.sh`, `profile_*.sql`, `verify_*.sql`, y las
**69 definiciones SQL** de los procedimientos relevantes en `backup/_work/procs/`.

---

## 2. Escala del legacy

| Métrica | Valor |
|---|---|
| Tablas | **598** (320 con datos, 278 vacías) |
| Columnas | 5.945 |
| Procedimientos / vistas / funciones / triggers | 1.193 / 387 / 306 / 205 |
| **Claves foráneas declaradas** | **1** en 598 tablas |
| CHECK constraints | 5 |

**Aviso:** el legacy casi no declara FKs ni CHECKs — la integridad la mantiene el código.
**No se puede confiar en joins por FK**: cada relación se validó contra datos reales.

### Tablas con más datos

| Tabla | Filas | Qué es |
|---|---:|---|
| `CC_PreciosHistorico` | 1.497.218 | Histórico de precios por artículo |
| `CS_SucesosTrabajos` | 956.506 | Sucesos de los trabajos |
| `CS_PoliticasxArticulo` | 484.357 | Política aplicable a cada artículo |
| `CG_ItemsFacturas` | 457.197 | Renglones de factura |
| `CK_ItemsMovStock` | 422.936 | Renglones de movimientos de stock |
| `CC_CostoHistorico` | 361.043 | Histórico de costos |
| `CS_AuditoriaTrabajos` | 211.565 | Auditoría de trabajos |
| `CS_Partes` | 128.561 | **Líneas de los trabajos** (repuestos/servicios) con `LiquidaComision` |
| `CS_UbicacionEquipoLog` | 92.394 | **Histórico de mesa/ubicación de cada equipo** |
| `CG_Facturas_Tabla` | 83.164 | **Facturas emitidas** (2009-10-16 → 2021-06-30) |
| `Intervienen` | 83.154 | **Quién intervino + comisiones** |
| `OrdenesLiquidadas` | 9.914 | Liquidaciones de orden (detalle) |
| `Liquidaciones` | 2.171 | Cabeceras de liquidación de orden |
| `CG_Pedidos_Tabla` | 70.199 | Pedidos |
| `CS_Trabajos` | 56.619 | **Órdenes de trabajo** |
| `CC_Articulos` | 33.349 | Catálogo de artículos |
| `CS_ComisionPartexInterviene` | 27.200 | Comisión por línea de trabajo por interviniente |
| `CK_ArticulosxDeposito` | 26.946 | Stock por depósito |
| `CC_Clientes_Tabla` | 14.730 | **Clientes** |
| `CC_Comisiones_Historico` | 11.403 | **Histórico de comisiones por artículo** (alimentado por trigger) |
| `CC_Comisiones` | 5.486 | Comisión por artículo / agrupación / esquema |
| `CG_Presupuestos_Tabla` | 157.428 | Presupuestos (2008 → 2021-06) |
| `CS_LiquidacionesTecnicos_Tabla` | 6 | Liquidaciones de técnicos |
| `CC_Usuarios` | 44 | **Personas: vendedores, técnicos, administración** |

---

## 3. Modelo de datos: las tablas que importan

### 3.1 `CS_Trabajos` — la orden de trabajo (143 columnas)

| Columna legacy | Significado real |
|---|---|
| `IDTrabajo` | PK interno |
| `NumeroOrden` | Número legacy **no único** y vacío en el 69 % (§5.1) |
| `Estado` | Estado del circuito, 10 valores (§3.3) |
| `FechaOrden` / `FechaAlta` | Ingreso / alta en el sistema |
| `FechaLista` / `FechaCerrada` | Listo / cierre |
| `FechaCobrada` / `MontoCobrado` | Cobro |
| `Responsable` | `CC_Usuarios.Codigo` de **quien recibe el equipo** |
| `Intervienen` | **Contador** de intervinientes (0-9), *no* un id de persona |
| `CodCli` | `CC_Clientes_Tabla.CodCli` — **0 = sin cliente vinculado** |
| `Cliente` | Nombre **copiado en la OT** (a veces aunque `CodCli` = 0) |
| `Equipo` | Tipo **con la marca adentro**: `LAVARROPAS DREAN` |
| `Modelo` / `NroSerie` | Modelo y serie |
| `Falla` | Motivo informado |
| `TrabajoRealizado` | **Qué se hizo** — el detalle de la tarea |
| `TotalPresupuesto` / `VentaTotal` / `CostoTotal` | Presupuesto / venta / costo |
| `VentaTotalComisiones` / `CostoTotalComisiones` | Parte de venta y costo que corresponde a comisiones |
| `Liquidada` / `FechaLiquidacion` / `LiquidacionNro` | **Liquidación de comisiones de la orden** |
| `FacturaEmitida` | **Número de factura** (formato `A0003-00007273`) — hasta 2021 |
| `Comprobante` | **Polimórfico**: número de factura `1816-00002755` *o* texto (`STOCK`, `FALTA FACTURA`) |
| `FechaComprobante` | Fecha del comprobante; **no** es la fecha de factura |
| `NroDocumento` | Nro. de documento del cliente en la OT |
| `Garantia` | tinyint de 3 estados (§4.2) |
| `DuracionGarantia` | Plazo en meses |
| `IDPolitica` | **Política aplicada** → define garantía / fuera de garantía |
| `Area` | Área = política (coinciden en 33.570 de 56.619) |
| `Ubicacion` / `IDUbic` / `TipoUbic` | **Dónde está el equipo / en qué mesa** (§4.6) |
| `Sucursal` | **Dominio sin usar**: `CC_Sucursales` está vacía |
| `TecnicoVisita` / `FechaVisita` / `AsistirEn` | Visita a domicilio |
| `Gestion` | Marca de gestión |

### 3.2 `Intervienen` — los técnicos y sus comisiones

| Columna | Significado |
|---|---|
| `Orden` (PK) | → `CS_Trabajos.IDTrabajo` |
| `Persona` (PK) | → `CC_Usuarios.Codigo` (**el técnico**) |
| `ComisionProductos` / `ComisionPartes` / `ComisionServicios` / `ComisionOtros` | Comisión del técnico por cada concepto |
| `Liquidacion` | Liquidación del técnico |
| `FechaLiquidacionTecnico` | Fecha de esa liquidación |
| `NroFactura` | **Factura con la que se le paga al técnico** (no cruza con `CG_Facturas_Tabla`) |
| `EstadoPresupuesto` / `DescripcionPresupuesto` / `FechaFinPresupuesto` | Estado y texto del presupuesto |

32.521 trabajos con 1 interviniente, 12.523 con 2, 6.365 con 3; **3.684 sin ninguno**.
**40 de las 77 personas que intervienen ya no existen** en `CC_Usuarios` (usuarios borrados):
32.798 filas de `Intervienen` (39,4 %) apuntan a un técnico sin nombre.

### 3.3 El circuito de estados (`dbo.CS_GetEstadoTrabajo`)

| `Estado` | Texto legacy | Significado |
|---:|---|---|
| `-1` | Esperando Recepción / Para Iniciar / Para Visitar | El equipo **aún no entró** (o va a domicilio) |
| 0 | Para Presupuestar | Hay que cotizar |
| 1 | Para Informar | Hay que comunicar el diagnóstico |
| 2 | En Aprobación | Esperando aprobación del cliente |
| 3 | Faltan Requisitos | Falta documentación del cliente |
| 4 | Abierta | **En taller, en reparación** |
| 5 | Rechazada | El cliente rechazó |
| 6 | Anulada (con motivo) | Anulada |
| 7 | Cerrada | Cerrada sin factura |
| 8 | **Liquidada** (sin factura) / **Facturada** (con factura) | **Terminada** |

Distribución: **8 → 49.993** (88 %), 6 → 5.747, 7 → 653, 5 → 127, 4 → 44, 2 → 3, 1 → 1,
0 → 1, NULL → 50.

El texto de `-1` depende de `TipoUbic IN (1,2)` (**el equipo está en el taller**) y de
`AsistirEn` (**visita a domicilio**).

### 3.4 `CC_Clientes_Tabla` — clientes (59 columnas)

| Columna | Significado |
|---|---|
| `CodCli` | PK |
| `Cliente` | Razón social o nombre (**288 nombres repetidos**) |
| `Tipo` | **No es persona/empresa**: catálogo `CC_TiposCliente` → 0 = "Clientes sin tipo definido" (14.725), 1 = "GREMIO MAYORISTAS" (5) |
| `Vendedor` | `CC_Usuarios.Codigo` — **11.178 sin vendedor, 2.147 en 0** |
| `Liquidar` | bit — sólo **42** clientes lo tienen activo |
| `ServiciosGarantia` | bit — sólo **28** (son las **marcas**: Whirlpool, New-San, BGH…) |
| `NuestroCodigo` | **Código que le da el cliente a su equipo** — la única referencia estructurada cliente→equipo |
| `CondicionVenta`, `CategoriaPrecio0..3`, `CreditoOtorgado` | Condiciones comerciales |
| `ContactoPrincipal` | → `CC_ContactosxCliente` (sólo 84 lo tienen, y **25 apuntan al contacto de otro cliente**) |
| `Telefonos` / `Email` | **El teléfono real está acá** (11.694 de 14.730 tienen; el email sólo 269) |

**El documento (CUIT/DNI) no está en la tabla de clientes**: vive en
`CG_Facturas_Tabla.CUIT` y hay que reconstruirlo por `CodCli`.

### 3.5 `CC_Usuarios` — las personas (44 filas)

PK = **`Codigo`** (no `ID`). Columnas: `Codigo`, `LoginName`, `Nombre`, `Password`,
`FechaCreacion`, `EMail`, **`Descripcion`**, `UltimoLogin`, `PermitirLogin`, `Anulado`,
`ClaveCiberCall`, `CreadoPor`, …

**El rol NO está en `Descripcion`** (vacío en 33 de 44). Está en **`CC_Tareas`** (7 filas):
`1 = Facturista`, **`2 = Vendedor`**, **`3 = Técnico`**, `4 = Administrativo`,
`5 = Fletero`, `6 = Agente`, `7 = Cajero`, y se asigna por usuario con
`CC_TareasxUsuario`. Hay **11 técnicos activos**.

### 3.6 `dbo.Areas` — NO son sucursales

63 filas. `Areas` = **centro autorizado de servicio de una marca**:

| Codigo | Area | Empresa | NuestraDenominacion |
|---:|---|---|---|
| 1 | WHIRLPOOL GARANTIAS | WHIRLPOOL ARGENTINA S.A. | CENTRO AUTORIZADO DE SERVICIO |
| 4 | SANYO GARANTIAS | NEW-SAN S.A. | CENTRO AUTORIZADO DE SERVICIOS |
| 12 | SINGER - MACOSER GARANTIAS | MCLEAN S.A.I.C.I.A. | CENTRO AUTORIZADO DE SERVICIOS |

Y `dbo.TiposTrabajos` (63 filas) define el tipo de trabajo por área: `FUERA` (55 áreas,
fuera de garantía) y los códigos de garantía `AGU`, `AAC`, `ASC`, `AGS`, `TGU`, `TAC`,
`TSC`, `TGS`.

`dbo.CC_Sucursales` está **VACÍA** ⇒ en el legacy **no hay sucursales**.

---

## 4. Perfil de los datos

### 4.1 Volumen y cobertura temporal

| Métrica | Valor |
|---|---|
| Trabajos totales | **56.619** |
| Rango | **2001-06-21 → 2026-10-21** (25 años) |
| `Estado = 8` (liquidadas/facturadas) | **49.993** (88,3 %) |
| Sin `NumeroOrden` | 13.925 (24,6 %) |
| Con `CodCli = 0` | **9.151 (16,2 %)** |
| Con `NroSerie` | 39.443 (69,6 %) |
| Con `TrabajoRealizado` | 50.347 (88,9 %) |
| Con `FacturaEmitida` | 7.135 (12,6 %) |
| Con `Comprobante` en formato factura | 4.699 |
| Con `FechaComprobante` | 25.993 (45,9 %) |

| Año | Total | Estado 8 | | Año | Total | Estado 8 |
|---|---:|---:|---|---|---:|---:|
| 2019 | 1.691 | 1.526 | | 2023 | 1.207 | 1.191 |
| 2020 | 1.294 | 1.245 | | 2024 | 1.474 | 1.290 |
| 2021 | 1.161 | 1.144 | | 2025 | 1.617 | 1.403 |
| 2022 | 1.366 | 1.363 | | 2026 | 1.197 | 870 |

### 4.2 Garantía / fuera de garantía — dónde está de verdad

`CS_Trabajos.Garantia` es un tinyint de **3 estados**:

| `Garantia` | Filas | Significado |
|---:|---:|---|
| 0 | 39.345 | **Fuera de garantía** |
| 1 | 17.273 | **En garantía** (de marca o de service) |
| 2 | 1 | Garantía propia |

Pero el flag **no basta**: la garantía real se resuelve por la **política** y por el
**plazo**:

```
CS_Trabajos.IDPolitica ──► Aux_PoliticasxArea (ID, Area, TipoTrabajo)   [126 filas]
    TipoTrabajo:  NULL → 63 áreas
                  FUERA → 55 áreas        ← FUERA DE GARANTÍA
                  AGU | AAC | ASC | AGS | TGU | TAC | TSC | TGS  → garantía

Regla de vencimiento (del propio código del legacy):
    si DATEDIFF(mm, @FechaComprobante, @Fecha) > @DuracionGarantia
        → RAISERROR 'La Garantía ha vencido'
```

Sobre las 16.351 OTs en garantía que tienen `FechaComprobante`: **16.245 con garantía
vigente** y sólo **106 vencidas** (0,6 %).

El **plazo** sale de `dbo.CS_ObtenerGarantiaProducto`, con esta jerarquía:
**producto → artículo → agrupación de artículos → política/área** (primero que encuentre).

**Consecuencia para la migración:** `Garantia` y `DuracionGarantia` **no se copian 1:1**.
Hay que derivar un estado nuevo a partir de (política, plazo, fecha) y **recalcular** el
vencimiento, no copiar el flag.

### 4.3 Empresa vs. persona

**En el legacy no existe el campo.** Ni `CC_Clientes_Tabla` ni ninguna tabla cliente tiene
una marca persona/empresa. `Tipo` es el **canal comercial** (`CC_TiposCliente`: "sin tipo
definido" / "GREMIÓ MAYORISTAS"), no el tipo de persona jurídica.

La distinción es **informal**, y hay que derivarla:

| Señal | Dónde | Cobertura |
|---|---|---|
| Sufijo societario en el nombre (`S.A.`, `S.A.C.I.F.`, `S.R.L.`, `LTDA.`, `S.A.E.C.A.`, `COOP`) | `CC_Clientes_Tabla.Cliente` | — |
| CUIT válido (11 dígitos con dígito verificador) | `CG_Facturas_Tabla.CUIT` por `CodCli` | 3.151 clientes (21,4 %), con placeholders (`100000`, `11111111`) |
| Que sea una **marca** (garantía) | `Areas.CodCli` + `ServiciosGarantia` | 28 clientes |

Indicio de que la empresa es una entidad de primer nivel: 288 nombres repetidos, entre
ellos **`NICOLAS GONZALEZ ODDONE S.A.E.C.A.` con 79 filas** y **`TRIPLEX LTDA.` con 79
filas** — misma empresa, **una fila por sucursal / punto de venta**. En el sistema nuevo
hay que decidir: ¿una `customers` por empresa agrupando, o una por sucursal?

### 4.4 Datos del cliente

| Métrica | Valor |
|---|---|
| Clientes | 14.730 |
| Con `Vendedor` | 3.552 (24,1 %) — de los cuales 2.147 con `Vendedor = 0` |
| Con `Liquidar = 1` | 42 |
| Con `ServiciosGarantia = 1` | 28 (las marcas) |
| Con teléfono real | 11.694 (79,4 %) |
| Con email | 269 (1,8 %) |
| Con CUIT recuperable | 3.151 (21,4 %) |
| Nombres repetidos | 288 grupos |

### 4.5 Equipos

**El legacy no tiene tabla de equipos**: el equipo vive desnormalizado dentro de cada
trabajo (`Equipo` + `Modelo` + `NroSerie`). El histórico de ubicación se apoya en el
`IDTrabajo`, no en un id de equipo.

Agrupando por `(CodCli, NroSerie)` y descartando los seriales sentinela (`ILEGIBLE` 575,
`FALTA` 286, `S/N` 214, `NO TIENE` 100):

- 38.268 trabajos con serie válida → **26.150 equipos distintos** `(cliente, serie)`.
- 24.780 series distintas; hay equipos con muchas OTs (p. ej. `PM0655` del cliente 7384: 67 OTs).

`Equipo` trae **la marca dentro del texto** y con mayúsculas/acentos inconsistentes:
`LAVARROPAS DREAN` (1.293), `AIRE ACONDICIONADO` (1.072), `LAVARROPAS AUTOMATICO ` (919),
`HELADERA WHIRLPOOL` (728), `heladera` (726), `HELADERA BAMBI` (706), `LAV.DREAN CONCEPT
5.05 V1` ⇒ hay **13.327 valores distintos** de `Equipo`: hay que **normalizar categoría y
marca** con un catálogo curado (no alcanza una heurística por palabra clave: sólo cubre
~55 %).

### 4.6 Mesas de trabajo

`CS_Trabajos.Ubicacion` (varchar 50, **sin catálogo**) top:

| Valor | OTs | | Valor | OTs |
|---|---:|---|---|---:|
| `TALLER` | 711 | | `TALLER - BOX B` | 51 |
| `TALLER-BOX1` | 101 | | `TALLER - BOX A` | 28 |
| `TALLER-BOX2` | 72 | | *(basura)* `Retirada el 18/06/2008` | 39 |
| `TALLER-BOX4` | 61 | | *(basura)* `c` | 32 |
| `TALLER-BOX3` | 60 | | | |

`CS_TipoUbicaciones` (10 filas) **no son mesas**: es el catálogo de **dónde está el
equipo** — `0 = Domicilio Cliente`, `1 = Taller Propio`, `2 = Taller Responsable`,
`3 = Comercio`, `4 = Terceros`, y 100-104 = los mismos "en tránsito hacia…".

El histórico es `CS_UbicacionEquipoLog` (92.394 filas, hasta 7 cambios por trabajo),
alimentado por el trigger `CS_ModificacionTrabajo` → `CS_EVENTO_TRABAJO_CambioUbicacion`.

**Quién asigna la mesa:** la persona que registra la recepción
(`dbo.CS_GrabarRecepcion` recibe `@Ubicacion` y `@TipoUbic`; el tipo lo deduce el sistema
con `CS_ObtenerTipoUbicacion` si no se pasa). **No hay validación contra un maestro.**

### 4.7 Trabajos internos

`Cliente = 'ELECTROTECNIREF'` (774 OTs) y `Falla = 'TRABAJO INTERNO'` (398): son
mantenimiento del propio taller (`Equipo = 'TALLER'`, `TotalPresupuesto = 0`,
`TrabajoRealizado` = "cambio de plafón", "instalación de cámaras en depósito nuevo").
**No deben migrarse como OT de cliente.**

---

## 5. Hallazgos que condicionan la migración

### 5.1 `NumeroOrden` no es único — bloqueante

El destino tiene `UniqueConstraint("company_id", "number")` en `work_orders` y genera el
correlativo **por empresa** (`WorkOrderCounter`).

Sobre 42.694 OTs con número:

| Clave candidata | Distintos | ¿Única? |
|---|---:|---|
| `NumeroOrden` solo | 12.886 | ❌ (hasta 60 repeticiones) |
| `Lugar + NumeroOrden` | 16.114 | ❌ |
| `Año + NumeroOrden` | 30.523 | ❌ |
| `Lugar + Año + NumeroOrden` | 34.968 | ❌ |
| `Sucursal + NumeroOrden` | 4.054 | ❌ |

Además, **desde 2020 las OTs nuevas no llevan `NumeroOrden`** (sólo hay números con
`FechaOrden` de 2018, 2019 y un caso de 2022).

**Conclusión:** el correlativo del sistema nuevo **no puede venir del legacy**. Hay que
usar el correlativo propio por empresa y guardar el `NumeroOrden` como referencia
(igual que hoy hace `work_order_import_rows.legacy_ficha`).

### 5.2 El 16 % de las OTs no tiene cliente vinculado

9.151 OTs con `CodCli = 0`, pero **el nombre del cliente está copiado en la OT**
(`GOMEZ REINERIO`, `LLANET GABRIEL`, `VILLANUEVA JONNY MAGNO`…). Recuperables emparejando
por nombre normalizado contra `CC_Clientes_Tabla`.

### 5.3 El documento del cliente es inservible como clave

3.151 de 14.730 clientes tienen CUIT, con placeholders (`100000` en 36.775 facturas,
`11111111` en 1.359). El `UniqueConstraint("company_id", "document")` del destino **no se
puede poblar con el CUIT legacy tal cual**: hay que validar el dígito verificador y, si no
pasa, dejar `document` en NULL con una clave de deduplicación alternativa.

### 5.4 La calidad de los datos modernos es alta

Sobre las 5.495 OTs de 2023 en adelante: con interviniente 5.446 (99,1 %), con
`TrabajoRealizado` 5.432 (98,8 %), con `FechaLista` 5.405 (98,4 %), con `VentaTotal`
5.209 (94,8 %), con `FacturaEmitida` 1.579 (28,7 %).

⇒ **Importar 2020+ es de alta calidad y bajo riesgo.** 2001-2019 es más ruidoso pero tiene
el mismo valor de archivo.

---

## 6. Los seis temas pedidos

### 6.1 Factura: fecha y número

**El número** (`CG_Facturas_Tabla.Numero`, varchar 14) tiene esta forma:

```
A0004-00002010
└┬┘└─┬─┘└──┬──┘
 │  │     │      └─ correlativo de talonario (8 dígitos, NO se reinicia por año)
 │  │     └──────── punto de venta (4 dígitos)
 │  └────────────── prefijo de grupo (CG_GruposDocumentos.Prefijo): A, B, C, E, X, M, Z, R
 └───────────────── grupo
```

- La **clave real** de una factura es **`(TipoDoc, Numero)`**: hay 18 números duplicados,
  todos por colisión `TipoDoc = 1` vs `TipoDoc = 31`.
- `TipoDoc` → `dbo.CC_TiposDocumentos` (34 filas): **1 = Factura**, **31 = Factura MiPyme
  (FCE)**. Sólo existen esos dos valores (83.146 y 18 facturas).
- La **fecha de factura** es **`CG_Facturas_Tabla.Fecha`** (default `getdate()`).
- `CS_Trabajos.FechaComprobante` **NO es la fecha de factura**: coincide en **1 de 3.494**
  casos.

**El vínculo factura ↔ OT no existe como tabla puente.** Hay dos mecanismos:

| Mecanismo | Dónde | Cobertura |
|---|---|---|
| Texto | `CS_Trabajos.FacturaEmitida` (varchar 20) | 7.135 OTs — pero sólo **3.494 (48,9 %)** encuentran factura |
| Items | `CG_ItemsFacturas` con `Tipo = 2` y `Referencia = CS_Trabajos.IDTrabajo` | 2.037 ítems → **2.011 OTs** (100 % de match) |
| Presupuesto | `CG_Facturas_Tabla.Cotizacion` → `CG_Presupuestos_Tabla.ID` | 83.164/83.164 |

Juntos resuelven **3.507 OTs de 56.619** (6,2 %).

**El `Comprobante` es polimórfico** — 4.699 OTs lo traen con formato factura
(`1816-00002755`), y **ninguna** de esas existe en `CG_Facturas_Tabla` (0 de 4.699):
son facturas emitidas en otro módulo. Los otros valores son textos de estado:

| Valor | OTs | Significado |
|---|---:|---|
| (vacío) | 30.679 | Sin comprobante |
| `NNNN-NNNNNNNN` | **4.699** | **Número de factura** |
| `NO CORRESPONDE` | 3.276 | Facturado a otro |
| `STOCK` | 2.405 | Salida de mercadería sin factura |
| `NO TIENE` | 1.454 | Sin factura |
| `FALTA FACTURA` | 1.384 | Factura pendiente |
| `SIN FACTURA` | 795 | — |
| `FALTA` | 528 | — |
| `FALTA FOTOCOPIA` | 250 | — |
| formatos viejos (`B5-2140`, `A8-1`, `FA 8…`) | ~150 | Numeración pre-2009 |

**Regla de importación:** `invoice_number` = `COALESCE(FacturaEmitida, Comprobante si
matchea `[0-9]{4}-[0-9]{8}`)`, y `issued_at` = `CG_Facturas_Tabla.Fecha` si la factura
resuelve, si no `FechaComprobante`. En total, **8.328 OTs** quedan con número de factura
(7.135 + 4.699 − 3.506 de solapamiento).

**`Intervienen.NroFactura` es otra cosa**: es la factura con la que se **liquida al
técnico** (`CS_LiquidacionesTecnicos.Factura`), y **no cruza** con `CG_Facturas_Tabla`
(0 de 27). No es una factura al cliente.

**Facturación electrónica: sí.** `CAI` + `VtoCAI` (código de autorización de impresión),
`TipoDoc = 31` = FCE MiPyme, `Incoterms`, `Afip_Pais`, `CodigoBarras`.

### 6.2 Mesas de trabajo

**Conclusión central: en el legacy la mesa es texto libre y no existe su maestro.**

| Tabla candidata a maestro | Filas | Qué es realmente |
|---|---:|---|
| `dbo.UBIC_Ubicaciones` | **0** | El maestro de mesas **previsto** (con `Ocupacion`, `Utilizado`, `Maximo`, `Capacidad`) — nunca se usó |
| `dbo.CS_Ubicaciones` | **0** | Maestro de mesas de taller — nunca se usó |
| `dbo.CK_Ubicaciones` | **0** | Ubicaciones de **stock en depósito**, no de taller |
| `dbo.CK_ArticulosxUbicacion` | **0** | Stock por ubicación de depósito |

(`dbo.CK_ArticulosxDeposito`, que sí tiene 26.946 filas, es stock por **depósito** — otra
cosa.)

El código legacy **sí usa** `UBIC_Ubicaciones` para controlar ocupación por módulos al
cambiar de ubicación (`CS_EVENTO_TRABAJO_CambioUbicacion` libera y reserva), pero como la
tabla está vacía, en la práctica **la mesa nunca se validó ni se contabilizó**.

Consecuencias:
- El sistema nuevo **puede inventar el maestro de mesas** (es una mejora real: `TALLER-BOX1`
  y `TALLER - BOX A` son la misma mesa escrita de dos maneras).
- El histórico importable es `CS_UbicacionEquipoLog` (92.394 filas) con
  `FechaDesde` / `FechaHasta` — **un trabajo puede tener hasta 7 cambios de mesa**.
- La mesa se asigna **en la recepción**, no en la reparación.

### 6.3 Empresa

Ver §4.3. En el legacy **no hay campo persona/empresa**; hay que derivarlo de:
1. CUIT válido (reconstruido desde `CG_Facturas_Tabla`),
2. sufijo societario en el nombre,
3. si es una marca (`Areas.CodCli` + `ServiciosGarantia`).

Y hay que decidir si las ~79 filas de una misma empresa son una `customers` con varias
direcciones o varias `customers`.

### 6.4 Técnicos

- **Rol**: `CC_Tareas.Tarea = 3` ('Tecnico'), asignado por `CC_TareasxUsuario`.
  **11 técnicos activos**. El rol de **vendedor** es `Tarea = 2`.
- **Nombre**: `CC_Usuarios.Codigo` = `Intervienen.Persona`. `CC_Usuarios.Descripcion`
  **no** sirve para el rol (vacío en 33 de 44).
- **Fantasmas**: 40 de las 77 personas que intervienen **no existen** en `CC_Usuarios`
  (32.798 filas de `Intervienen`, 39,4 %). `GetNombreUsuario` devuelve `'Sistema'` en ese
  caso ⇒ **el nombre visible en el legacy es "Sistema"**, no el del técnico real.
- `CS_Trabajos.Responsable` = quien recibe el equipo (71 distintos, 39 ya borrados).
- **Stock del técnico**: `CK_StockTecnico` (51.645 movimientos, **abandonado el 2020-02-11**),
  con un depósito virtual `IDDeposito = -Tecnico` en `CK_ArticulosxDeposito`.
- **Calzones, zonas, recorridos, líneas y calendario por técnico** existen
  (`CS_ZonasxTecnico`, `CS_RecorridoTecnico`, `CS_CalendarioxTecnico`, `CS_LineasxTecnico`,
  `CS_ExpertiseTecnico`): son de un **módulo de campo (móvil)** que no es parte del
  núcleo y no se migraría.

### 6.5 Comisiones

En el legacy hay **tres motores distintos** y no deben mezclarse:

| | **Motor de TRABAJOS** (service) | **Motor de VENTAS** (mostrador) | **Motor de ARTÍCULOS** |
|---|---|---|---|
| Proc | `CS_CalcularComisionesTrabajo` → `CS_CalcularComisionItem` | `CC_ComisionesVentas` | `CC_ComisionesxEsquema` |
| Origen | `CS_Partes` (líneas de la OT) | `CG_ItemsFacturas` / `CG_ItemsCreditos` | `CC_Articulos` + `CC_Agrupaciones` |
| **Persiste** | **Sí** → `Intervienen.Comision*` + `CS_ComisionPartexInterviene` | **No** (es un SELECT de reporte) | No |
| Destinatario | El técnico que intervino | El **vendedor** | — |

#### 6.5.1 Qué es un «vendedor»

**No hay columna "es vendedor" en `CC_Usuarios`** (19 columnas, ninguna de rol). El oficio
se define por una **tarea**: `dbo.CC_Tareas` (7 filas) —
`1 Facturista`, **`2 Vendedor`**, **`3 Tecnico`**, `4 Administrativo`, `5 Fletero`,
`6 Agente`, `7 Cajero` — y se asigna por persona en `CC_TareasxUsuario`.

- **16 de 44 usuarios** tienen la tarea 2 (vendedor). Un mismo usuario puede ser vendedor
  **y** técnico (ej. `96 Flores Nicolas` tiene las tareas 1, 2, 3 y 4).
- La lista que usa la pantalla es `dbo.CC_TraerUsuariosComisiones` → `CC_Usuarios_Visibles`
  → `fn_ListaUsuarios(@ListaTareas, …)`, filtrando por tarea `'2'` (vendedor) o `'3,6'`
  (técnico + agente).
- El vendedor aparece en **dos lugares distintos**: `CC_Clientes_Tabla.Vendedor` (el
  asignado al cliente) y `CG_ItemsFacturas.Vendedor` / `CG_Facturas_Tabla.Vendedor` (el del
  comprobante). **Son las dos puntas de la comisión de ventas.**

#### 6.5.2 Comisión del técnico — la fórmula (verificada contra los datos)

El orquestador es `dbo.CS_CalcularComisionesTrabajo(@IDTrabajo)`:

1. **Guardas**: sin `CS_Trabajos.IDPolitica` o con `Estado < 0` no calcula nada.
2. **Blanqueo**: `UPDATE Intervienen SET Comision* = NULL WHERE Orden=@IDTrabajo AND
   Liquidacion IS NULL` ⇒ **sólo se recalcula lo no liquidado** (una vez liquidado, la
   comisión es inmutable).
3. **Cursor** sobre `CS_Partes WHERE NroOrden=@IDTrabajo AND COALESCE(LiquidaComision,-1) <> 0`.
4. Por cada parte: `CS_CalcularComisionItem` y el reparto en `Intervienen`.
5. `CS_ObtenerTotalesTrabajo` recalcula `VentaTotal`, `CostoTotal`, `VentaTotalComisiones`,
   `CostoTotalComisiones`.

**La fórmula nuclear** (`CS_CalcularComisionItem`) — el modo y el porcentaje salen de la
**política** (`CS_PoliticasxArea`, por `CS_Trabajos.IDPolitica`), según la categoría de la
línea (`CS_Partes.Tipo`: 0 Producto, 1 Repuesto, 2 Servicio, 3 Otros):

| Modo | Cálculo | Configuración |
|---:|---|---|
| 1 | `monto × cantidad` (importe fijo) | `MontoComision*` como importe |
| 2 | `venta × cantidad × pct/100` (**% venta**) | `ComisionProd/Rep/Serv/Otro = 2` |
| **3** | **`(venta − costo) × cantidad × pct/100` (% utilidad)** | `ComisionProd/Rep/Serv/Otro = 3` |
| 4 | `costo × cantidad × pct/100` (% costo) | `ComisionProd/Rep/Serv/Otro = 4` |
| 5 | según el **esquema** de comisión del usuario | `CC_Comisiones` |
| 0 | sin comisión | — |

`venta` y `costo` pasan por `dbo.CC_ConvertiraMoneda` (redondeo a los decimales de la
moneda **antes** de multiplicar) y por la cotización de la línea.

**Verificación numérica** (recalculé la fórmula en SQL y la comparé contra
`CS_Partes.CostoComision` guardado): **coincide en 41.480 de 55.408 líneas de servicio
(75 %)**; el resto difiere por el redondeo de moneda. Ejemplos reales:

| OT | Venta | Costo | Cant | % | Calculado | **Guardado** |
|---:|---:|---:|---:|---:|---:|---:|
| 57942 | 13.223,14 | 0 | 3 | 50 % | 19.834,71 | **19.834,71** ✔ |
| 57906 | 49.586,78 | 0 | 1 | 50 % | 24.793,39 | **24.793,39** ✔ |
| 47794 | 431,00 | 215,50 | 1 | 50 % | 107,75 | **107,75** ✔ |
| 48803 | 493,65 | 246,81 | 1 | 50 % | 123,42 | **123,42** ✔ |
| 48887 | 661,157025 | 1,00 | 1 | 50 % | 330,0799 → 330,08 | **330,08** ✔ |
| 55704 | 0 | 17.000 | 1 | 50 % | **−8.500** | **−8.500** ✔ (costo > venta) |

> **Corrección importante:** la base **no** es "el importe de las partes" sino
> **`(precio de venta − costo) × cantidad`**. Coincide con una primera aproximación
> ingenua sólo en los casos con costo 0, que son la mayoría en este dump.

**El reparto: `CS_Partes.LiquidaComision`** es el interruptor real de la comisión:

| `LiquidaComision` | Destinatario |
|---:|---|
| `0` | **la línea no genera comisión** (67.807 de ~121.000 partes) |
| `-1` | **todos** los intervinientes, **dividido** entre ellos |
| `-2` | el `CS_Trabajos.Responsable` |
| `-3` | el `CS_Partes.Provee` (si es 0 → comisión 0) |
| `> 0` | ese usuario concreto, **sin dividir** |

El divisor es `COUNT(*) FROM Intervienen WHERE Orden = @IDTrabajo` (con guarda de división
por cero), y la suma va a la columna según la categoría: `ComisionProductos` (0),
`ComisionPartes` (1), `ComisionServicios` (2), `ComisionOtros` (3).

**Caso verificado de reparto** — OT 56265: una parte de servicio, venta 44.000, cantidad 1
⇒ comisión bruta 22.000, repartida entre **3** intervinientes ⇒ **7.333,3333** cada uno.

**La configuración por área** (`CS_PoliticasxArea` es una **vista sobre `dbo.Areas`** con 97
columnas):

| `Liquidar` | `Garantia` | Áreas | `MontoComisionServ` | `ComisionServ` (modo) |
|---:|---:|---:|---:|---:|
| 0 | 1 (garantía) | 61 | **50 %** | 3 (% utilidad) |
| 0 | 0 | 8 | 50 % (6 con comisión) | 3 |
| 0 | 2 | 2 | 50 % | 3 |
| 3 | 0 (fuera de garantía) | 55 | **50 %** | 3 |

El área 49 ("ELECTRICIDAD") suma además **5 %** sobre productos y repuestos.
En la práctica **sólo el servicio se commissiona** (50 % de utilidad) y producto/repuesto
casi nunca (61 casos en garantía y 368 fuera, donde un técnico lo reclamó explícitamente
con `LiquidaComision` = su id).

#### 6.5.3 Liquidación del técnico

```
CS_Partes.LiquidaComision
  ↓  CS_CalcularComisionesTrabajo / CS_CalcularComisionItem
  ↓  CS_ComisionPartexInterviene (27.200 filas: el detalle línea a línea)
CP_ItemsLiquidacionTecnico
  ↓  CS_GrabarLiquidacionTecnico
CS_LiquidacionesTecnicos_Tabla (cabecera, 6) + CS_OrdenesLiquidadasTecnicos (detalle, 28)
  ↓
UPDATE Intervienen SET Liquidacion, FechaLiquidacionTecnico, NroFactura
```

| Campo | Significado |
|---|---|
| `Intervienen.Liquidacion` | nº de liquidación que **cubre a esa persona** en esa orden (NULL = pendiente) |
| `Intervienen.FechaLiquidacionTecnico` | fecha de esa liquidación |
| `Intervienen.NroFactura` | **documento contra el que se cobra** la comisión del técnico |

Liquidaciones reales (las 6): `1` → Allione Adrian, factura `A0004-00000228`, total
1.611,57 (2016-05-03); `2`-`6` → 2019-06-30/07-08, facturas `01-01`…`01-04`, totales
366,06 / 2.488,998 / 3.234,131 / 891,438 / 0,00. Las **27** filas de `Intervienen` con
`Liquidacion IS NOT NULL` suman exactamente los totales de cabecera.

La liquidación de la **orden** (negocio → cliente) es otro circuito:
`dbo.CS_LiquidarOrden` pasa el estado **7 → 8** y escribe `CS_Trabajos.Liquidada`,
`FechaLiquidacion`, `LiquidacionNro` (FK a `dbo.Liquidaciones`, 2.171 filas) y
`FacturaEmitida`; el detalle queda en `dbo.OrdenesLiquidadas` (9.914). **Bloquea si
`CS_Trabajos.Gestion <> 0`** ("está detenido por una auditoría").

#### 6.5.4 Comisión del vendedor — cómo se liquidan y cómo se cargan

**La comisión del vendedor NO se persiste en ninguna tabla.** `CC_ComisionesVentas` es un
**SELECT de reporte** que corre sobre las facturas del período y devuelve el detalle línea
por línea; el legacy no guarda el resultado. Para migrar hay que **recalcular y persistir**.

**El vendedor es el del comprobante**, no el del cliente:
`COALESCE(CG_ItemsFacturas.Vendedor, CG_Facturas_Tabla.Vendedor)`.

**El esquema de comisión** de cada vendedor sale de
`dbo.CC_EsquemaComisionVenta(@Vendedor, @IDPolitica)` → `CC_ComisionxUsuario` → `CC_EsquemasComision`.

**El porcentaje** se resuelve por cascada:

```
valor = COALESCE( CC_Comisiones.Valor (override por artículo),
                   CC_Comisiones.Valor (override por agrupación, IDArticulo < 0),
                   CC_EsquemasComision.ValorComisionProducto / Repuesto / Servicio / Otros )

tipo  = COALESCE( CC_Comisiones.Tipo,
                   CC_Comisiones.Tipo (agrupación),
                   CASE CategoríaDelArtículo WHEN 0 THEN Producto WHEN 1 THEN Repuesto
                                              WHEN 2 THEN Servicio WHEN 3 THEN Otros END )
```

**El importe** es `Unitario × Cantidad × Valor / 100` (lo aplica la aplicación, que es
quien llama al procedimiento).

**Las tres políticas** (`CC_PoliticasComisionVendedor`) deciden **quién cobra**:

| `@Politica` | Descripción | Regla |
|---:|---|---|
| 1 | Vendedor del comprobante | Cobra el que hizo la venta |
| 2 | Vendedor del cliente | Cobra el asignado al cliente, **sólo si es distinto** del del comprobante |
| 3 | Vendedor del cliente y del comprobante | Sólo si **coinciden** los dos |

**Y hay un cuarto caso: los créditos.** `CC_ComisionesVentas` incluye
`CG_Creditos` con el mismo esquema y **unitario en negativo** ⇒ las devoluciones
**descontan** la comisión.

**Filtro importante:** `@Incluir = 1` ⇒ sólo facturas **cobradas**
(`COALESCE(CG_SaldosFacturas.Saldo, 0) = 0`).

**Configuración real** (`CC_ComisionxUsuario`: `ID | IDUsuario | IDEsquema | IDPolitica |
IDModulo | Activo` — `IDModulo`: 0 = trabajos, 1 = ventas):

| Usuario | Esquema | Política | Módulo | Activo |
|---|---|---:|---:|---:|
| 67 Graef German | 2 (10 %) | 27 | 0 trabajos | sí |
| 6 FYH | 2 (10 %) | 3 | 1 ventas | sí |
| 6 FYH | 3 (3 %) | 2 | 1 ventas | sí |
| 6 FYH | 2 (10 %) | 1 | 1 ventas | sí |

Los dos esquemas (`CC_EsquemasComision`):

| Esquema | Producto | Repuesto | Servicio | Otros | Tope |
|---|---|---|---|---|---|
| 2 — "Esquema 10 %" | modo 2, **10 %** | modo 2, **10 %** | modo 1, 0 % | modo 1, 0 % | — |
| 3 — "Esquema 3 %" | modo 2, **3 %** | modo 2, **3 %** | — | — | 0 % |

**Quién vende realmente** (por `CG_Facturas_Tabla.Vendedor`):

| Vendedor | Facturas | Total |
|---|---:|---:|
| 71 Gómez Maria José (Administración) | 1.659 | 69,8 M |
| 40 Rodriguez Debora (ADMINISTRATIVA) | 46.921 | 49,6 M |
| 69 Noguera Adriana | 16.801 | 33,4 M |
| 1 Administrador | 5.705 | 21,3 M |
| 38 Lopez Samuel | 4.652 | 15,3 M |
| 78 Sommer Alfredo (Viajante) | 154 | 7,3 M |
| 17, 66, 6, 75, 72, 43, 81, 42, 55 | | resto |

De las 83.164 facturas: **todas** tienen vendedor en el comprobante; 69.707 tienen cliente
con vendedor; **sólo 4.818 coinciden** ⇒ **en el 94 % de las ventas quien vende NO es el
vendedor asignado al cliente**. Eso es exactamente lo que arbitran las 3 políticas.

#### 6.5.5 Qué condiciones activan o desactivan el cálculo

| # | Condición | Efecto |
|---|---|---|
| 1 | `CS_Trabajos.IDPolitica IS NOT NULL` y `Estado >= 0` | sin política no se calcula nada |
| 2 | `CS_Partes.LiquidaComision = 0` | la línea no genera comisión |
| 3 | `CS_Partes.LiquidaComision = -3` y `Provee = 0` | comisión 0 |
| 4 | `Π.ComisionProd/Rep/Serv/Otro <> 0` | define el `LiquidaComision` inicial (`-1` todos, `-2` responsable, `-3` provee) |
| 5 | **`Intervienen.Liquidacion IS NULL`** | **una vez liquidado, la comisión es inmutable** |
| 6 | `Π.ComisionSobreVigentesAlGenerar0..3 = 1` | usa costo/venta vigentes a la fecha de alta |
| 7 | `Π.ComisionEsCosto0..3 = 1` | la comisión **excluye** el costo del bien del `CostoTotal` |
| 8 | `CS_Trabajos.Gestion <> 0` | auditoría: **impide liquidar** la orden |

**Sobre `CC_Clientes_Tabla.Liquidar` (42 clientes con el flag activo):** lo consume **un
solo** módulo, `CS_EntregarProducto`, y **invierte** la decisión de liquidar
automáticamente esa orden al entregar el equipo. **No afecta al cálculo de la comisión** —
el interruptor real es `CS_PoliticasxArea.Liquidar` + `CS_Partes.LiquidaComision`.

**Sobre la garantía:** la garantía **no es un flag de "sin comisión"**. El corte real es
(1) la **política** (que define modo y porcentaje por categoría) y (2) el
`LiquidaComision` de la línea. La garantía sólo altera la base **indirectamente**, vía
precio y costo: en `CS_InsertaConsumo`, con `@Garantia = 1` el precio de venta se infla
(`@Unitario = @Costo * (1 + @PorcUtil/100)`), y como el modo 3 es "% utilidad", **la
garantía de terceros infla la comisión**; con `@Garantia = 2` se infla el costo y la
reduce. Además, en garantía de terceros el cliente real pasa a ser el de la marca
(`@CodCli = CASE WHEN P.Garantia=1 AND P.CodCli>0 THEN P.CodCli ELSE @CodCli`).

**La escala de descuentos por demora** (`CS_PorcentajeEscalaComision`) está **muerta**:
no la invoca ningún módulo y su tabla (`CS_EscalasDescuentosEsquema`) tiene **1 sola fila**
con porcentaje 0. **Hay que decidir explícitamente si se replica.**

#### 6.5.6 Lo que NO se puede determinar desde la base

- **`CS_Trabajos.VentaTotalComisiones`**: ningún SP lo calcula; llega como parámetro a
  `CS_GrabarTrabajo`. En los ejemplos observados coincide con `VentaTotal`, pero **su regla
  exacta no es determinable** desde el dump.
- **Dónde y cómo se cobra la comisión de ventas de mostrador**: el legacy **no la
  persiste** ⇒ no es determinable.
- **La semántica de `CC_Clientes_Tabla.Tipo` y `CategoriaPrecio0..3`**: no intervienen en
  ningún cálculo de comisión.
- **La intención de negocio del flag `CC_Clientes_Tabla.Liquidar`**: el comportamiento
  está confirmado (invierte la liquidación automática), la intención no.
- **La configuración real de esquemas**: `CC_EsquemasComision` tiene 2 filas y las 5.486
  filas de `CC_Comisiones` usan todas el esquema 3 ⇒ el módulo de esquemas está poblado
  como **demo**, no como producción. El motor está completo; la configuración real no.

### 6.6 Garantía y fuera de garantía

Ver §4.2. Resumen:

| Concepto | Dónde | Cómo se calcula |
|---|---|---|
| ¿Está en garantía? | `CS_Trabajos.Garantia` (0/1/2) **y** la política (`IDPolitica` → `Aux_PoliticasxArea.TipoTrabajo`) | `TipoTrabajo = 'FUERA'` ⇒ fuera |
| ¿Cuánto dura? | `CS_Trabajos.DuracionGarantia` y/o `dbo.CS_ObtenerGarantiaProducto` | Jerarquía producto → artículo → agrupación → política/área |
| ¿Venció? | `DATEDIFF(mm, FechaComprobante, Fecha) > DuracionGarantia` | El propio legacy aborta con *"La Garantía ha vencido"* |

**Verificado sobre 16.351 OTs en garantía con `FechaComprobante`: 16.245 vigentes (99,4 %)
y 106 vencidas.**

---

## 7. Brechas del schema destino

El destino actual tiene: `companies`, `customers`, `equipment`, `equipment_categories`,
`work_orders`, `work_order_statuses`, `work_order_events`, `work_order_quotes` (+items),
`work_order_diagnoses`, `work_order_execution_items`, `work_order_final_tests`,
`work_order_evidence`, `work_order_import_batches/rows`, `equipment_documents`, `users` /
`company_users`, `roles`, `permissions`, `parameter_definitions`, `company_parameters`,
módulos de IA y de notificaciones.

**No existe** nada de: vendedor, comisión, garantía, factura, mesa de trabajo, técnico
como entidad, ni `work_order` → técnico.

| Necesidad del legacy | Origen legacy | ¿Existe en el destino? | Acción propuesta |
|---|---|---|---|
| Vendedor | `CC_Clientes_Tabla.Vendedor` → `CC_Usuarios` (tarea 2) | ❌ | `sellers` + `customers.seller_id` |
| Comisión de vendedor | `CC_ComisionesVentas` (al vuelo, **no se persiste**) | ❌ | `seller_commission_schemes` + `seller_commissions` (hay que **recalcular**) |
| Comisión de técnico | `Intervienen.Comision*` + `CS_ComisionPartexInterviene` + `CS_Partes.LiquidaComision` | ❌ | `work_order_parts` + `work_order_technicians` (4 cubos) |
| Modo y % de comisión | `CS_PoliticasxArea.Comision* / MontoComision*` (vista sobre `Areas`) | ❌ | `work_policies` (por área/política) |
| Esquema de comisión | `CC_EsquemasComision`, `CC_ComisionxUsuario`, `CC_Comisiones`, `CC_Comisiones_Historico` | ❌ | `commission_schemes`, `commission_scheme_users`, `commission_scheme_items` (+ histórico) |
| Liquidación de comisiones | `CS_LiquidacionesTecnicos_Tabla` + `CS_OrdenesLiquidadasTecnicos`; `Liquidaciones` + `OrdenesLiquidadas` | ❌ | `commission_settlements` + `commission_settlement_orders` |
| Garantía / fuera de garantía | `IDPolitica` → `Aux_PoliticasxArea.TipoTrabajo` + `DuracionGarantia` | ❌ | `work_orders.warranty_status` (ENUM) + `work_policies` |
| Empresa vs persona | nombre + CUIT (derivado) | ⚠️ `customer_type` existe | poblarlo con la heurística §4.3 |
| Técnico | `Intervienen.Persona` → `CC_Usuarios.Codigo` | ❌ | `technicians` + `work_order_technicians` |
| Línea de trabajo (repuesto/servicio) | `CS_Partes` (128.561) con `Tipo`, `LiquidaComision`, `Provee` | ⚠️ (`work_order_execution_items`) | `work_order_parts` con `liquida_comision` |
| Factura (fecha y número) | `CG_Facturas_Tabla` + `CS_Trabajos.FacturaEmitida/Comprobante` | ❌ | `invoices` + `work_orders.invoice_id` |
| Mesa de trabajo | `CS_Trabajos.Ubicacion`, `CS_UbicacionEquipoLog` | ❌ | `work_areas` (maestro nuevo) + `work_order_work_areas` |
| Número legacy de OT | `CS_Trabajos.NumeroOrden` | ⚠️ (`legacy_ficha` en la tabla de importación) | `work_orders.legacy_number` |
| Facturación de mano de obra | `CS_Trabajos.VentaTotal/CostoTotal` | ⚠️ (`work_order_execution_items`) | migrar a ítems de ejecución |

---

## 8. Plan de importación propuesto

> **Todavía no implementado.** Este informe es el paso previo.

### 8.1 Clientes — 14.730 filas

- Nombre, domicilio, localidad, **teléfono de `CC_Clientes_Tabla.Telefonos`** (el de la
  tabla de contactos no sirve: sólo tiene 90 filas).
- `customer_type`: **COMPANY** si hay CUIT válido o sufijo societario; **PERSON** si no.
- `document`: CUIT **sólo si pasa el dígito verificador**; si no, NULL.
- Deduplicar los 288 nombres repetidos: agrupar por nombre normalizado y consolidar.
- `seller_id`: desde `Vendedor` (ojo con `Vendedor = 0` ⇒ sin vendedor).

### 8.2 Equipos — 26.150 equipos `(cliente, serie)`

- `equipment_categories`: catálogo curado a partir de los ~60 `Equipo` más frecuentes
  (13.327 valores distintos ⇒ normalizar mayúsculas, tildes, y separar marca).
- `serial_number` = `NroSerie`, descartando `ILEGIBLE` / `FALTA` / `S/N` / `NO TIENE`.
- `model` = `Modelo`.
- Sin serie ⇒ agrupar por `(cliente, equipo, modelo)` o crear equipo por trabajo.

### 8.3 Tareas realizadas — las 49.993 en `Estado = 8` (+ opcionalmente las 653 en `Estado = 7`)

| Destino | Origen legacy |
|---|---|
| `number` | correlativo **propio** por empresa (NO el legacy) |
| `legacy_number` | `NumeroOrden` |
| `received_at` | `FechaAlta` (o `FechaOrden` si existe) |
| `completed_at` | `FechaLista` |
| `delivered_at` | `FechaCerrada` |
| `reported_fault` | `Falla` |
| `notes` | `TrabajoRealizado` |
| `status` | según §3.3, creando «Anulada» y «Rechazada» en la empresa destino |
| `customer_id` | `CodCli`; si es 0 → emparejar por nombre o crear |
| `equipment_id` | `(CodCli, NroSerie)` |
| `warranty_status` | **derivado** de la política + plazo (§4.2) |
| `invoice_id` / `invoice_number` | §6.1 |
| `work_order_import_rows` | una fila por OT con el volcado crudo (`legacy_fields`) para no perder nada y poder auditar |

### 8.4 Equivalencia de estados

| Legacy | Texto legacy | Estado destino |
|---:|---|---|
| -1 | Esperando Recepción / Para Iniciar / Para Visitar | Recibido |
| 0 | Para Presupuestar | Presupuestado |
| 1 | Para Informar | En diagnóstico |
| 2 | En Aprobación | Esperando aprobación |
| 3 | Faltan Requisitos | En diagnóstico *(revisar)* |
| 4 | Abierta | En reparación |
| 5 | Rechazada | **crear** «Rechazada» |
| 6 | Anulada | **crear** «Anulada» |
| 7 | Cerrada | Listo |
| 8 | Liquidada / Facturada | Listo (`marks_completed`), o Entregado (`marks_delivered`) si hay factura |

### 8.5 Importar también la dimensión de comisiones (recomendado)

Si el sistema nuevo va a liquidar comisiones, hay que migrar además:

| Origen legacy | Filas | Destino |
|---|---:|---|
| `CS_PoliticasxArea` (vista sobre `Areas`) | 126 | `work_policies` (modo + % de comisión por categoría, `Utilidad`, `Garantia`, `Liquidar`) |
| `dbo.Areas` | 63 | `work_areas` (marca / centro autorizado de servicio) |
| `CC_EsquemasComision` | 2 | `commission_schemes` |
| `CC_ComisionxUsuario` | 4 | `commission_scheme_users` (**con `modulo` para desambiguar políticas**) |
| `CC_Comisiones` | 5.486 | `commission_scheme_items` (artículo > 0 / agrupación < 0) |
| `CC_Comisiones_Historico` | 11.403 | `commission_scheme_items_history` |
| `CS_Partes` | 128.561 | `work_order_parts` (con `tipo` y `liquida_comision`) |
| `CS_ComisionPartexInterviene` | 27.200 | `work_order_part_commissions` (detalle línea a línea) |
| `Intervienen` | 83.154 | `work_order_technicians` (con los 4 cubos de comisión) |
| `CS_LiquidacionesTecnicos_Tabla` + `CS_OrdenesLiquidadasTecnicos` | 6 + 28 | `commission_settlements` + `commission_settlement_orders` |
| `Liquidaciones` + `OrdenesLiquidadas` | 2.171 + 9.914 | `order_settlements` + `order_settlement_orders` |
| `CC_Usuarios` + `CC_TareasxUsuario` | 44 + n | `users` + `roles` (vendedor / técnico / facturista / …) |

**Reglas que hay que replicar tal cual** (del §6.5):

1. El modo de comisión (1 importe fijo / 2 % venta / 3 % utilidad / 4 % costo / 5 esquema)
   y el porcentaje salen de la **política**, no del artículo.
2. La base es **`(venta − costo) × cantidad × pct/100`**, con redondeo de moneda **antes**
   de multiplicar.
3. `liquida_comision` (0 / −1 todos / −2 responsable / −3 provee / >0 usuario) decide el
   destinatario; con −1 se **divide entre los intervinientes**.
4. Una vez liquidado, la comisión es **inmutable**: todo update lleva
   `WHERE liquidacion_id IS NULL`.
5. `cliente.liquidar` **invierte** la liquidación automática de sus órdenes; no toca el
   cálculo de la comisión.
6. La comisión de ventas de mostrador **no está persistida** en el legacy ⇒ hay que
   **recalcularla** con la fórmula de `CC_ComisionesVentas` y decidir dónde se guarda.

### 8.6 Riesgos

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| 1 | `NumeroOrden` no es único | Rompe el unique del destino | Correlativo propio + `legacy_number` |
| 2 | CUIT ausente o placeholder en 79 % de los clientes | Unique `(company_id, document)` inservible | `document` nullable + dedup por nombre normalizado |
| 3 | 9.151 OTs sin cliente vinculado | Huérfanos | Emparejar por nombre; si no, cliente nuevo |
| 4 | Garantía en la política, no en el flag | Dato incorrecto si se copia 1:1 | Derivar y **recalcular** el estado de garantía |
| 5 | `Comprobante` polimórfico | Números de factura basura | Parsear con regex `^[0-9]{4}-[0-9]{8}$` |
| 6 | Trabajos internos (`TRABAJO INTERNO`) | Contaminan el histórico | Excluir o marcar |
| 7 | Equipos desnormalizados, marca en el texto | Categorías y marcas sucias | Normalizar con catálogo curado |
| 8 | Mesas como texto libre | Historial de mesas inutilizable | Crear maestro `work_areas` y mapear sin fuzzy aggressive |
| 9 | 1 sola FK declarada en 598 tablas | Joins dudosos | Validar cada relación (§4) |
| 10 | 40 de 77 técnicos borrados | Nombres perdidos | Importarlos como "técnico desconocido (legacy)" con el código |

---

## 9. Pendientes

- [ ] Cerrar la decisión de **persona vs empresa** (heurística CUIT + nombre) y si las 79
      filas de una misma empresa son una `customers` o varias.
- [ ] Decidir si se importa **todo el histórico (2001-2026)** o sólo desde 2020.
- [ ] Cerrar el **modelo de comisiones** del destino: ¿liquidación por orden, por
      vendedor, por mes? ¿Se replica la de ventas de mostrador (que el legacy no
      persiste) o se descarta?
- [ ] Decidir si se replica la **escala de descuentos por demora**
      (`CS_PorcentajeEscalaComision`, muerta en el legacy) y la **liquidación de técnicos**
      (6 cabeceras, 27 renglones: ¿o se recalcula desde cero?).
- [ ] Decidir el **modelo de mesas**: crear `work_areas` con maestro real, o seguir con
      texto libre.
- [ ] Decidir si las **facturas** son entidad propia (`invoices`) o sólo campos en la OT.
- [ ] Extensión del schema destino (Alembic): `sellers`, `technicians`,
      `work_order_technicians`, `work_order_parts`, `work_order_part_commissions`,
      `work_policies`, `commission_schemes`, `commission_scheme_users`,
      `commission_scheme_items`, `commission_settlements`, `order_settlements`,
      `work_orders.warranty_status`, `invoices`, `work_areas`,
      `work_order_work_areas`, `work_orders.legacy_number`.
- [ ] Importador **SQL Server → MySQL** (el XLSX no sirve para 56.619 OTs).
- [ ] Bitácora de la migración con conteos, muestra de 20 registros por entidad y cuadre
      importado vs. origen.

---

*Informe generado sobre la base restaurada. Las cifras salen de consultas SQL sobre los
datos reales, no de la lectura del código legacy.*
