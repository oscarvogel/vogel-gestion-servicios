# Plan: incorporar CiberBrain (CiberBase) al sistema y agregar el cierre mensual a marcas

> **Estado:** decisiones tomadas (2026-10-22). Implementación **pendiente de 4 respuestas** (§9).
> Base del análisis: `docs/informe-migracion-ciberbrain.md` (todo verificado sobre la base restaurada).
> Fecha: 2026-10-22.

---

## 0. Qué vamos a hacer, en una línea

Crear una **empresa nueva en staging**, ampliar el schema con las entidades que hoy no
existen (marca/área, garantía, factura, vendedor, técnico, comisiones, mesa), **importar**
clientes + equipos + órdenes de trabajo + líneas desde el backup, y agregar el **cierre
mensual a marcas** (qué OTs están en garantía y a qué empresa hay que liquidarle).

**El cierre mensual a marcas es lo que más valor aporta y hoy no existe en ningún lado:**
el legacy tampoco lo tiene (genera un reporte a mano; las OTs en garantía nunca se
"liquidan" porque su política tiene `Liquidar = 0`).

---

## 1. Decisiones tomadas (2026-10-22)

Las 4 decisiones bloqueantes están contestadas. Las 2 restantes quedan con **default
asumido**, anotado y reversible (se cambia antes de escribir la migración, o con un script
de ajuste sobre lo ya importado).

| # | Decisión | Respuesta | Consecuencia técnica |
|---|---|---|---|
| 1.1 | ¿Una empresa o una por marca? | **Una sola empresa: "Electrotecniref"** | Las marcas son *clientes* dentro de la empresa; `work_areas` es la dimensión de marca |
| 1.2 | Persona vs. empresa | **CUIT válido o sufijo societario → `COMPANY`; resto `PERSON`**, y **los 288 nombres repetidos se consolidan** en un cliente (las sucursales quedan como direcciones) | Default asumido (reversible) |
| 1.3 | ¿Desde cuándo se importa? | **Desde 2020** | **9.316 OTs** (8.506 terminadas `E8`, 646 cerradas `E7`, 164 en otros estados) |
| 1.4 | ¿Qué importe se liquida? | **El COSTO (`CostoTotal`)** | El cierre suma `SUM(unit_cost × quantity)` de las líneas |
| 1.4b | ¿Reporte o registro? | **Las dos cosas**: reporte + período registrado (`draft → issued → settled`) | Tablas `warranty_settlements` + `warranty_settlement_orders` |
| 1.5 | Mesas | **Maestro normalizado `work_benches`** | Default asumido (reversible) |
| 1.6 | Comisiones | **Se migra el resultado ya calculado** (`Intervienen.Comision*`), no se recalcula | Los esquemas/políticas quedan para una etapa siguiente |

**Lo que las decisiones implican y no estaba obvio:**

- Con 1.1, el cierre mensual es **un filtro**, no un cruce entre empresas: se agrupa por
  `work_areas.billing_customer_id` (que sale de `Areas.CodCli`, nunca de `Areas.Empresa`).
- Con 1.4, el importe a liquidar **no existe como campo en el destino**: hay que
  reconstruirlo desde `work_order_parts` (el legacy lo tiene en `CS_Trabajos.CostoTotal`).
- Con 1.3, las **OTs sin cliente** (5.969 de 9.316 = 64 %) entran igual: se emparejan por
  nombre o se crean con un cliente "sin identificar". **No bloquean el cierre**, porque el
  cierre se agrupa por *empresa a liquidar* (el área), no por cliente final.
- Con 1.6, **el sistema nuevo no puede recalcular comisiones todavía**: cambiar el porcentaje
  de un técnico hay que hacerlo por SQL sobre `work_order_technicians`.

---

## 1.b El modelo real de garantía del legacy (corregido sobre la base restaurada)

Esta sección **reemplaza** la lectura simplificada del informe. La garantía del legacy
**no es un campo: son dos tablas encajadas**, y entenderlas es lo que define el cierre.

### 1.b.1 Las dos capas

```
dbo.Areas (63 filas)                  -- una fila por MARCA / área de trabajo
   Codigo, Area, CodCli (a quién se le factura), Empresa (texto viejo),
   GarantiasTerceros (0..3), Liquidar, PeriodoGarantia, Comision*, ...

dbo.TiposTrabajos (Area, Codigo, ...)  -- sub-tipos dentro de un área
   Codigo: 'FUERA', 'AGU', 'AAC', 'ASC', 'AGS', 'TGU', 'TAC', 'TSC', 'TGS'
   Garantia (0..3), Liquidacion (0..3), Utilidad, PedirPartes, ...

dbo.Aux_PoliticasxArea (ID, Area, TipoTrabajo)   -- 126 filas = la POLÍTICA real
   TipoTrabajo NULL = política "Principal" de esa área
   TipoTrabajo 'FUERA' = sub-política "fuera de garantía" de esa área

CS_Trabajos.IDPolitica --> Aux_PoliticasxArea.ID
```

`CS_PoliticasxArea` es una **vista** que une las dos capas y expone `Garantia` y `Liquidar`
ya resueltos por tipo de trabajo. `Garantia` vale:

| Valor | Significado | De dónde sale |
|---|---|---|
| **0** | Fuera de garantía | `TiposTrabajos.Garantia` de la fila `FUERA` |
| **1** | Garantía de fábrica / terceros | `Areas.GarantiasTerceros` (principal) o `TiposTrabajos.Garantia` |
| **2** | Garantía propia / de service | `TiposTrabajos.Garantia` (sólo Alladio) |

### 1.b.2 `Liquidar` NO es "quién paga"

`Areas.Liquidar` / `TiposTrabajos.Liquidacion` definen **el ciclo de vida de la OT**, no la
deuda. Semántica sacada de `proc_CS_EstadoPosible`:

| Valor | Significado |
|---|---|
| **0** | No se liquida **automáticamente** (exige liquidación manual) |
| **1** | Se liquida automáticamente al cerrarse (pasa a `Estado = 8`) |
| **2** | **No se liquida nunca** |
| **3** | No se liquida automáticamente (exige manual) |

> `IF (@Liquidar = 0 OR @Liquidar = 3) AND @LiquidacionManual = 0 SET @EstadoPosible = 7`
> `IF @Liquidar = 2 SET @EstadoPosible = 7`

En la práctica: **las áreas de marca tienen `Liquidar = 0` en la política principal y
`Liquidar = 3` en la rama `FUERA`**. Ninguna tiene `2`. Por eso el legacy nunca automate el
`Estado = 8` en garantía, y por eso **no existe ningún cierre a marcas registrado**.

**Conclusión operativa: "a quién se liquida" es exclusivamente `Areas.CodCli`.** El flag de
garantía sólo dice si el trabajo es de fábrica o no.

### 1.b.3 Hallazgo: la rama `FUERA` **también se factura a la marca`

Como la rama `FUERA` pertenece a un área que tiene `CodCli`, las OTs "fuera de garantía" de
esa marca **se le facturan a la marca igual**. Medido sobre el corte 2020+:

| Empresa a liquidar | OTs garantía (`Gt=1`) | Costo garantía | OTs fuera de garantía **de la marca** (`Gt=0`) | Costo fuera | **Total OTs** | **Costo total** |
|---|---:|---:|---:|---:|---:|---:|
| DREAN S.A. | 1.586 | 17.741.140,83 | 748 | 5.661.609,04 | 2.334 | 23.402.749,87 |
| BGH S.A. | 180 | 3.126.586,59 | 1.038 | 27.242.781,84 | 1.218 | 30.369.368,43 |
| ELECTROLUX ARGENTINA S.A. | 91 | 287.314,55 | 193 | 1.671.227,20 | 284 | 1.958.541,75 |
| NEW-SAN S.A. | 10 | 9.804,00 | 183 | 1.411.771,50 | 193 | 1.421.575,50 |
| BAMBI | 74 | 539.886,68 | 144 | 976.880,18 | 218 | 1.516.766,86 |
| BRIKET S.A. | 131 | 1.064.800,00 | 54 | 250.562,07 | 185 | 1.315.362,07 |
| WHIRLPOOL ARGENTINA S.R.L. | 38 | 118.723,32 | 371 | 2.951.423,71 | 409 | 3.070.147,03 |
| RADIO VICTORIA TCL ARGENTINA S.A. | 91 | 700.125,06 | 73 | 903.679,54 | 164 | 1.603.804,60 |
| CARRIER S.A. | 0 | 0,00 | 82 | 1.473.006,63 | 82 | 1.473.006,63 |
| AUTOSAL S.A. | 136 | 777.202,00 | 151 | 1.129.138,98 | 287 | 1.906.340,98 |
| FRIMETAL S.A. | 36 | 262.252,65 | 95 | 750.969,53 | 131 | 1.013.222,18 |
| KRONEN INTERNACIONAL S.A. | 16 | 16.517,01 | 71 | 532.940,49 | 87 | 549.457,50 |
| EL DORADO S.A. | 36 | 296.548,20 | 30 | 401.664,59 | 66 | 698.212,79 |
| ORBIS MERTIG S.A.I.C. | 3 | 665,00 | 53 | 402.492,34 | 56 | 403.157,34 |
| **JOSE M. ALLADIO E HIJOS S.A.** | **304** | **174.081,12** | **0** | **0,00** | **304** | **174.081,12** |
| LONGVIE S.A. | 58 | 168.158,80 | 27 | 203.459,29 | 85 | 371.618,09 |
| HECTOR CODINI S.A. | 20 | 39.311,00 | 21 | 68.887,88 | 41 | 108.198,88 |
| ROTOPLAS ARGENTINA S.A. | 11 | 20.170,51 | 5 | 22.280,63 | 16 | 42.451,14 |
| INDESIT ARGENTINA S.A. | 0 | 0,00 | 32 | 149.448,90 | 32 | 149.448,90 |
| LG ELECTRONICS ARGENTINA S.A. | 0 | 0,00 | 61 | 300.087,43 | 61 | 300.087,43 |
| resto (14 empresas con volumen) | | | | | | |
| **TOTAL con empresa a liquidar** | **2.853** | **25.356.252,43** | **3.565** | **47.822.741,72** | **6.418** | **73.178.994,15** |
| **Sin empresa (`CodCli = 0`)** | 0 | 0,00 | 2.898 | 28.195.156,35 | 2.898 | 28.195.156,35 |
| **TOTAL 2020+** | 2.853 | 25.356.252,43 | 6.463 | 76.017.898,07 | **9.316** | **101.374.150,50** |

**Las dos cifras que definen el alcance del cierre mensual:**

| Criterio | OTs | Costo a liquidar (2020+) |
|---|---:|---:|
| **A — sólo garantía** (`Gt = 1`) | 2.853 | **25.356.252,43** |
| **B — todo lo que tiene empresa a liquidar** (`Gt = 1` + `Gt = 0` de marca) | 6.418 | **73.178.994,15** |

La diferencia es de **3.565 OTs y 47,8 M**: el trabajo "fuera de garantía" que las marcas
pagan igual (por acuerdo comercial), que es la mayor parte del movimiento.

### 1.b.4 Caso aparte: Alladio (CodCli 7634)

Alladio **no es una marca de fábrica**: es un *service oficial / representante*. Por eso no
tiene rama `FUERA` y sus áreas están nombradas distinto. Las 9 políticas del área 60:

| Política | Descripción | `Gt` | OTs 2020+ | Costo 2020+ |
|---|---|---:|---:|---:|
| `AGU` | Gtia Alladio - 1. CATD - Garantía usuarios | 1 | 289 | 168.310,37 |
| `ASC` | Gtia Alladio - 3. Stock de Comercio | 1 | 12 | 3.826,50 |
| `AAC` | Gtia Alladio - 2. CATD - Atenciones Comerciales | 1 | 1 | 340,00 |
| `TGU` | Terceras Marcas - 1. CATD - Garantía Usuarios | 1 | 1 | 743,75 |
| `AGS` | Gtia Alladio - 4. Garantia de Service | **2** | 0 | 0,00 |
| `TAC` / `TSC` / `TGS` | Terceras Marcas - 2/3/4 | 1 / 1 / **2** | 0 | 0,00 |
| Principal | Alladio | 1 | 1 | 860,50 |
| **Total** | | | **304** | **174.081,12** |

**Las OTs fuera de garantía de equipos Alladio caen en el área genérica `CodCli = 0`**, o
sea que hoy **no se le liquida nada a Alladio por ese lado**. Hay que decidir con el usuario si
corresponde liquidarle también lo fuera de garantía.

### 1.b.5 La regla de inclusión del cierre (definitiva)

> **Una OT entra al cierre mensual si su política pertenece a un área con `CodCli <> 0`,
> y se le imputa al cliente de ese `CodCli`.**

En el destino:

```sql
WHERE wa.billing_customer_id IS NOT NULL          -- el área tiene empresa a liquidar
  AND wo.completed_at >= :from AND wo.completed_at < :to
```

Y `work_areas` tiene que guardar **las dos capas del legacy** (`Areas` + `TiposTrabajos`),
no una sola:

```sql
work_areas(
  id, company_id FK,
  code VARCHAR(10),              -- 'WHIRLPOOL GARANTIAS'
  area_name VARCHAR(100),        -- dbo.Areas.Area
  policy_code VARCHAR(20),       -- 'FUERA' | 'AGU' | 'AAC' | 'ASC' | 'AGS' | 'TGU' | 'TAC' | 'TSC' | 'TGS' | NULL
  policy_description VARCHAR(100),-- TiposTrabajos.Descripcion
  is_principal BOOLEAN,          -- TipoTrabajo IS NULL
  billing_customer_id BIGINT FK customers,  -- Areas.CodCli -> clientes
  brand_name VARCHAR(100),       -- Areas.Empresa (texto legacy, DESALENTADO)
  warranty_type TINYINT,         -- 0=fuera, 1=terceros, 2=propia  (Garantia)
  liquidate_mode TINYINT,        -- 0=manual, 1=auto, 2=nunca, 3=manual (Liquidar)
  warranty_period_months SMALLINT,
  commission_service_mode TINYINT, commission_service_pct DECIMAL(9,2),
  commission_product_mode TINYINT, commission_product_pct DECIMAL(9,2),
  commission_part_mode    TINYINT, commission_part_pct    DECIMAL(9,2),
  commission_other_mode   TINYINT, commission_other_pct   DECIMAL(9,2),
  utility INT,
  active BOOLEAN,
  UNIQUE(company_id, area_name, policy_code)
)
```

**Ojo con dos trampas del texto legacy ya detectadas:**

| Área | `Areas.Empresa` (texto) | Real (por `CodCli`) |
|---|---|---|
| 14 | ARISTON GARANTIAS / ARGENTRON S.A. | `CodCli = 5` = **INDESIT ARGENTINA S.A.** |
| 29 | HITACHI GARANTIAS / RADIO VICTORIA FUEGUINA | `CodCli = 7767` = **RADIO VICTORIA TCL ARGENTINA S.A.** |
| 21 | DAIKIN GARANTIAS | `CodCli = 7` = **BGH S.A.** |
| 19 | FEDDERS GARANTIAS | `CodCli = 7` = **BGH S.A.** |

Además hay **áreas de una marca que facturan a otra** (Whirlpool tiene `CONSUL`, `ESLABON DE
LUJO`; `NEW-SAN` tiene CANDY, DE LONGHI, DATANDHOME). Con `CodCli` eso se resuelve solo.

---

## 2. Fase 0 — Empresa nueva en staging

Staging es **Coolify** (`staging-frontend`, `staging-backend`, `staging-db`), **deploy
manual**, y el contenedor de backend corre `alembic upgrade head` al arrancar.

```bash
# 1. Crear la empresa (el endpoint ya crea empresa + estados + admin + rol)
curl -X POST https://<staging>/api/v1/companies \
  -H "Authorization: Bearer <superadmin>" -H "Content-Type: application/json" \
  -d '{"name":"Electrotecniref","slug":"electrotecniref",
       "legal_name":"ELECTROTECNIREF S.A.","tax_id":"",
       "admin_email":"admin@electrotecniref.com.ar",
       "admin_password":"<gen>", "admin_full_name":"Administrador"}'
```

Eso crea: la fila en `companies`, los **8 estados por defecto** (Recibido → Entregado), el
usuario admin y el rol "Administrador" con todos los permisos.

**Después:**
1. Correr las migraciones de la Fase 1 contra `staging-db`.
2. Verificar que `alembic upgrade head` corre limpio (hay un test de migraciones:
   `backend/tests/test_migrations.py` — ojo con `DATABASE_URL`).
3. Importar sólo **10 marcas + sus clientes facturadores** como prueba de humo antes de
   importar nada masivo.

**Cuidado con el orden de deploys:** la bitácora de `sesion-2026-10-02.md` registra que
producción auto-deploya al mergear a `main` y **staging queda en la versión anterior hasta
que se lo despierte a mano**. O sea: **mergear a `main` despliega producción**. Si todavía
no queremos tocar producción, hay que trabajar en una rama y deployar staging a mano.

---

## 3. Fase 1 — Extensión del schema (Alembic)

Una migración, en este orden (de lo más chico a lo más grande), con las FKs en cascada
según `company_id`:

### 3.1 Entidades de catálogo

> **`work_areas` guarda las DOS capas del legacy** (`Areas` + `TiposTrabajos`), no una sola.
> El esquema completo, ya corregido, está en §1.b.5. Sin esto el cierre mensual no puede
> distinguir "garantía de la marca" de "fuera de garantía de la misma marca", que **también
> se liquida a la marca** (1.b.3).

```sql
-- work_areas = Areas + TiposTrabajos + Aux_PoliticasxArea (126 políticas)
-- Ver §1.b.5 para el esquema completo y el porqué de cada columna.

-- sellers = los VENDEDORES (CC_Usuarios con tarea 2)
sellers(id, company_id FK, name, legacy_code INT, user_id BIGINT NULL FK users, active BOOLEAN)

-- technicians = los TÉCNICOS (CC_Usuarios con tarea 3)
technicians(id, company_id FK, name, legacy_code INT, user_id BIGINT NULL FK users, active BOOLEAN)

-- work_benches = las MESAS (decisión 1.5: maestro normalizado)
work_benches(id, company_id FK, name, normalized_code, active BOOLEAN)
```

### 3.2 Extensiones de `work_orders`

El modelo actual (`backend/app/models/work_order.py`) tiene `status` (String 30) **y**
`status_id` (FK a `work_order_statuses`), y `received_by_user_id` **NOT NULL**. La
importación tiene que respetar las dos cosas.

```sql
ALTER TABLE work_orders
  ADD COLUMN legacy_number     VARCHAR(20) NULL,   -- NumeroOrden (NO único: va como referencia)
  ADD COLUMN warranty_status    VARCHAR(20) NULL,   -- 'warranty' | 'out_of_warranty' | 'own_warranty'
  ADD COLUMN work_area_id       BIGINT NULL FK work_areas,   -- la marca
  ADD COLUMN legacy_policy_code INT NULL,          -- Areas.Codigo original
  ADD COLUMN legacy_liquidated  BOOLEAN NULL,      -- CS_Trabajos.Liquidada
  ADD COLUMN legacy_guarantee   TINYINT NULL,       -- CS_Trabajos.Garantia crudo
  ADD COLUMN work_bench_id      BIGINT NULL FK work_benches;
```

**Dos trampas del schema destino:**

| Trampa | Qué hay que hacer |
|---|---|
| `work_orders.status` es un **String**, no el id del estado | La equivalencia legacy (`Estado` int) se resuelve contra `work_order_statuses` → se llena **`status_id`** (FK) **y** el string en `status`, para que los dos queden consistentes. Ojo: `work_orders.status` está indexado y el service (`work_orders.py`) compara contra los strings de `status.name`. |
| `work_orders.received_by_user_id` es **NOT NULL** | Es `CS_Trabajos.Responsable` (el que recibió el equipo) → `users.id`. **39 de los 71 responsables del legacy ya no existen** como usuarios ⇒ hace falta un usuario técnico de respaldo ("Importación / legacy") y mapearlos a ese. Igual con los técnicos: **40 de las 77 personas que intervinieron están borradas**. |

### 3.3 Tablas nuevas de la OT

```sql
-- líneas de trabajo (CS_Partes)
work_order_parts(
  id, company_id FK, work_order_id FK work_orders,
  line_no INT, part_type TINYINT,              -- 0 producto, 1 repuesto, 2 servicio, 3 otros
  description VARCHAR(500), item_code VARCHAR(60),
  quantity DECIMAL(19,6), unit_price DECIMAL(19,6), unit_cost DECIMAL(19,6),
  currency_id INT, cost_currency_id INT,
  commission_recipient_type TINYINT,   -- 0=nadie, -1=todos, -2=responsable, -3=proveedor
  commission_recipient_id BIGINT NULL, -- técnico_id cuando >0
  supplier_technician_id BIGINT NULL,
  commission_amount DECIMAL(19,6),
  is_cost_excluded BOOLEAN
)

-- quién intervino + comisiones (Intervienen)
work_order_technicians(
  id, company_id FK, work_order_id FK work_orders, technician_id FK technicians,
  commission_products DECIMAL(19,6), commission_parts DECIMAL(19,6),
  commission_services DECIMAL(19,6), commission_other  DECIMAL(19,6),
  settlement_id BIGINT NULL, settled_at DATETIME NULL, settlement_invoice VARCHAR(20),
  UNIQUE(work_order_id, technician_id)
)

-- detalle de comisión por línea (CS_ComisionPartexInterviene)
work_order_part_commissions(
  id, work_order_part_id FK work_order_parts, technician_id FK technicians,
  amount DECIMAL(19,6)
)

-- facturas (CG_Facturas_Tabla)
invoices(
  id, company_id FK, customer_id FK customers,
  number VARCHAR(20), series VARCHAR(5), point_of_sale SMALLINT, sequence_number BIGINT,
  invoice_type VARCHAR(20),            -- 'factura' | 'factura_mipyme'
  status VARCHAR(20),                 -- 'issued' | 'cancelled'
  issued_at DATETIME,                 -- CG_Facturas_Tabla.Fecha  <-- LA fecha de factura
  due_date DATETIME, created_at DATETIME,
  gross_amount DECIMAL(19,6), net_amount DECIMAL(19,6), total_amount DECIMAL(19,6),
  tax_id VARCHAR(15),                  -- CUIT
  cae VARCHAR(15), cae_expires_at DATETIME,
  seller_id BIGINT NULL FK sellers,    -- vendedor del comprobante
  work_order_id BIGINT NULL FK work_orders,   -- cuando la factura nació de una OT
  legacy_id INT,                      -- CG_Facturas_Tabla.ID
  UNIQUE(company_id, invoice_type, number)
)

-- cierre mensual a marcas (NUEVO: no existe en el legacy)
warranty_settlements(
  id, company_id FK,
  period DATE,                        -- primer día del mes liquidado
  billing_customer_id BIGINT FK customers,   -- la empresa a liquidar
  work_area_id BIGINT NULL FK work_areas,    -- la marca
  status VARCHAR(20),                 -- 'draft' | 'issued' | 'settled' | 'cancelled'
  works_count INT, total_amount DECIMAL(19,6),
  generated_at DATETIME, issued_at DATETIME, settled_at DATETIME,
  UNIQUE(company_id, period, billing_customer_id, work_area_id)
)
warranty_settlement_orders(
  id, warranty_settlement_id FK warranty_settlements,
  work_order_id FK work_orders, amount DECIMAL(19,6),
  UNIQUE(warranty_settlement_id, work_order_id)
)
```

### 3.4 Decisiones de schema pendientes de respuesta

Tres cosas del schema que **no** dependen de las respuestas de §9, con la recomendación que
propongo (si no contestan, se aplica el default y se anota):

| Tema | Recomendación | Por qué |
|---|---|---|
| **Presupuestos** (`CG_Presupuestos_Tabla`, 157.428) | **Sólo el total** (`TotalPresupuesto` de la OT), como un campo en `work_orders` | Los items del presupuesto son 157 mil filas para un dato que hoy nadie usa en el cierre. Traerlos multiplica el importador sin agregar valor al requerimiento. |
| **Facturas** (`CG_Facturas_Tabla`, 83.164) | **Sólo las vinculables a una OT** (3.507) + las que nacieron de una OT vía `Comprobante` (4.699) | El resto es facturación mostrador sin OT: no entra al cierre ni a la operación. La tabla completa se puede importar después, en otra etapa, como histórico contable. |
| **Moneda / cotización** | **Congelar el tipo de cambio** en la línea (`unit_cost` y `unit_price` en la moneda de la empresa, guardando el `cotizacion` original) | El destino no tiene tabla de monedas ni cotizaciones. Congelar preserva el número sin inventar una tabla de cambios que nadie pidió. Si se prefiere la moneda original, hay que agregar `currencies` + `exchange_rates` y eso es otra migración. |

**Los dos defaults de §1 que sí quedan sin confirmar** (persona/empresa y mesas) se resuelven
en la Fase 1 con los defaults asumidos y se ajustan después con un script si el usuario cambia
de idea: son reversibles sin rehacer la migración.

---

## 4. Fase 2 — Importador

**No es el importador de XLSX que ya existe** (`work_order_import_service.py`): ese lee
planillas. Esto es un script Python que lee del contenedor SQL Server y escribe en MySQL.

### 4.1 Diseño

```
backend/scripts/import_cyberbrain.py       # CLI
backend/scripts/import_cyberbrain/
  source.py        # lee del contenedor SQL Server (sqlcmd / pymssql) con paginación
  mappers.py       # reglas de mapeo campo a campo (en un solo lugar, testeable)
  steps/
    01_areas.py    02_customers.py  03_equipment.py
    04_work_orders.py  05_parts.py  06_technicians.py  07_invoices.py
  report.py        # cuadre importado vs origen
```

**Cómo leer el origen — dos caminos, y hay que elegir uno:**

El contenedor `cb-sql` **no publica puerto** (se levantó sin `-p`), así que desde Windows no
hay acceso directo por TCP. Las dos opciones:

| Opción | Cómo | Ventaja | Inconveniente |
|---|---|---|---|
| **A — publicar el puerto + driver Python** (recomendada) | recrear el contenedor con `-p 1433:1433` y agregar `pymssql` a `pyproject.toml` (o a un extra `[project.optional-dependencies] import`) | El importador lee paginado y con tipos reales; se puede re-ejecutar fácil | Hay que instalar el driver en el venv de Windows |
| **B — exportar CSV desde el contenedor** | `sqlcmd -o` / `bcp` por tabla, y el importador lee los CSV | Cero dependencias nuevas | Un paso más; los CSV de `CS_Partes` (128.561) y `CG_ItemsFacturas` (457.197) son pesados |

Las dependencias del backend están en **`backend/pyproject.toml`** (no hay
`requirements.txt`): `fastapi, uvicorn, sqlalchemy, pymysql, alembic, pydantic-settings,
python-jose, passlib, bcrypt, python-multipart, email-validator, tzdata, httpx`.
**No hay driver de SQL Server**: hay que agregarlo o ir por la opción B.

- **Destino**: SQLAlchemy contra `DATABASE_URL`, con `company_id` fijo (la empresa nueva).
- **Idempotencia**: cada lote escribe en `work_order_import_rows` (ya existe) con
  `legacy_id` + `legacy_fields` crudo, para poder re-ejecutar sin duplicar y auditar.
- **Velocidad**: 10.079 OTs + 26.150 equipos + 128.561 líneas ⇒ batch inserts de 1.000,
  `executemany`, y las referencias resueltas por un mapa en memoria (`CodCli → id`,
  `(CodCli, NroSerie) → id`).

**Restricciones NOT NULL del destino que condicionan el mapeo** (verificadas en los
modelos):

| Tabla | Campo | Origen legacy |
|---|---|---|
| `work_orders` | `customer_id`, `equipment_id`, `reported_fault`, `received_by_user_id`, `status` | `CodCli`, `(CodCli, NroSerie)`, `Falla`, `Responsable`, `Estado` |
| `equipment` | `customer_id`, `category_id` | `(CodCli, NroSerie)`, categoría curada de `Equipo` |
| `customers` | `name`, `customer_type` | `Cliente`, derivado (decisión 1.2) |

### 4.2 Mapeos clave (ya determinados)

| Destino | Origen legacy | Regla |
|---|---|---|
| `customers.name` | `CC_Clientes_Tabla.Cliente` | normalizado (mayúsculas, espacios) |
| `customers.document` | `CG_Facturas_Tabla.CUIT` por `CodCli` | **sólo si pasa el dígito verificador**; si no, NULL |
| `customers.customer_type` | derivado | CUIT válido o sufijo societario → `COMPANY`; si no `PERSON` |
| `customers.phone` | `CC_Clientes_Tabla.Telefonos` | el de la tabla de clientes (la de contactos tiene 90 filas) |
| `customers.seller_id` | `CC_Clientes_Tabla.Vendedor` | si es 0 o NULL → NULL |
| `equipment.serial_number` | `CS_Trabajos.NroSerie` | descartar `ILEGIBLE`, `FALTA`, `S/N`, `NO TIENE` |
| `equipment.category_id` | `CS_Trabajos.Equipo` | **catálogo curado** (13.327 valores distintos ⇒ hay que normalizar; los 60 más frecuentes cubren el grueso) |
| `work_orders.number` | — | **correlativo propio** por empresa (el legacy no sirve) |
| `work_orders.legacy_number` | `CS_Trabajos.NumeroOrden` | referencia, no único |
| `work_orders.received_at` | `CS_Trabajos.FechaAlta` | o `FechaOrden` si existe |
| `work_orders.completed_at` | `CS_Trabajos.FechaLista` | |
| `work_orders.delivered_at` | `CS_Trabajos.FechaCerrada` | |
| `work_orders.reported_fault` | `CS_Trabajos.Falla` | |
| `work_orders.notes` | `CS_Trabajos.Work**ajoRealizado**` | + metadatos legacy |
| `work_orders.customer_id` | `CS_Trabajos.CodCli` | si es 0 → emparejar por nombre; si no, crear |
| `work_orders.status_id` + `status` | `CS_Trabajos.Estado` | equivalencia contra `work_order_statuses` (crear «Anulada» y «Rechazada») |
| `work_orders.received_by_user_id` | `CS_Trabajos.Responsable` | → `users.id`; los 39 responsables borrados → usuario de respaldo |
| `work_orders.warranty_status` | `CS_PoliticasxArea.TipoTrabajo` | `FUERA` → `out_of_warranty`; área `Garantia=1` → `warranty` |
| `work_orders.work_area_id` | `CS_Trabajos.IDPolitica` → `Areas` | **la marca** |
| `work_orders.invoice_id` | `CG_Facturas_Tabla` vía `FacturaEmitida` o `Comprobante` | parsear con regex `^[0-9]{4}-[0-9]{8}$`; issued_at = `Fecha` |

### 4.3 Orden de ejecución (por FK)

Volúmenes **medidos** sobre el corte 2020+ (no estimados):

```
1. work_areas (políticas)            126 filas   (63 áreas x {Principal, FUERA, ...})
2. customers (incluye las marcas) 14.730 filas   <- las marcas se importan como clientes
3. sellers / technicians              44 filas   (11 técnicos activos, 16 vendedores)
4. equipment + equipment_categories  5.213 filas   <- pares (cliente, serie) del corte
5. work_orders                       9.316 filas   (8.506 E8 + 646 E7 + 164 otros)
6. work_order_parts                 29.799 filas
7. work_order_technicians           18.383 filas
8. invoices                          ~8.000 filas   (3.507 por FacturaEmitida + 4.699 por Comprobante)
```

**Ojo con los que no entran y por qué:**

- `work_orders` del corte 2020+ traen **5.969 OTs sin cliente** (64 %). Se emparejan por
  nombre contra `CC_Clientes_Tabla`; los que no matchean quedan con un cliente
  "sin identificar" y una marca `legacy_unidentified`. **No bloquean el cierre**, que se
  agrupa por *empresa a liquidar*.
- Los **equipos** se deduplican por `(cliente, serie)`: 5.213 en el corte, contra 26.150
  estimados a ojo sobre la base completa. El número real del histórico entero es mayor.

---

## 5. Fase 3 — El cierre mensual a marcas (el requisito nuevo)

### 5.1 Qué tiene que responder

> *"a fin de mes tienen que saber qué órdenes están en garantía y a qué empresa hay que liquidarla"*

Entonces, para un período (mes):

1. **Resumen**: por **empresa a liquidar** ⇒ cuántas OTs, importe total.
2. **Detalle**: cada OT con cliente final, equipo, modelo, serie, técnico, importe y fecha.
3. **Filtros**: período, empresa/marca, estado del cierre.
4. **Cierre**: poder "emitir" el período (congelarlo) y marcarlo liquidado.

### 5.2 La regla de oro: tres campos del legacy no sirven

| Usar | No usar | Por qué |
|---|---|---|
| `Areas.CodCli` → cliente | `Areas.Empresa` | `Areas.Empresa` es **texto desactualizado**: el área 14 dice `ARISTON GARANTIAS / ARGENTRON S.A.` pero factura a `CodCli = 5` = **INDESIT ARGENTINA S.A.** El área 29 dice `HITACHI / RADIO VICTORIA FUEGUINA` pero factura a `RADIO VICTORIA TCL`. Hay además áreas de una marca que facturan a otra (`DAIKIN` → BGH, `FEDDERS` → BGH, `CONSUL`/`ESLABON DE LUJO` → WHIRLPOOL, `CANDY`/`DE LONGHI`/`DATANDHOME` → NEW-SAN). |
| `CS_PoliticasxArea.Garantia` | `CS_Trabajos.Garantia` | Discrepan en **184 OTs**. La política es la fuente autoritativa (17.089 coherentes vs 17.273 del flag). |
| `Areas.CodCli` | `Areas.Liquidar` / `TiposTrabajos.Liquidacion` | `Liquidar` define el **ciclo de vida** de la OT (0/3 = liquidación manual, 1 = automática, 2 = nunca), **no a quién se le paga**. Confundir los dos es el error más caro posible acá: con `Liquidar = 0` se excluiría justo la garantía, que es lo que hay que liquidar. |

### 5.3 Endpoint

```http
GET /api/v1/warranty-settlements?period=2026-06
GET /api/v1/warranty-settlements/{id}
POST /api/v1/warranty-settlements/generate   { period: "2026-06" }  -> crea/actualiza los drafts
POST /api/v1/warranty-settlements/{id}/issue
POST /api/v1/warranty-settlements/{id}/settle
```

Respuesta del resumen (los números son **reales**, medidos sobre junio 2025):

```json
{
  "period": "2025-06",
  "companies": [
    { "billing_customer_id": 16, "billing_customer_name": "DREAN S.A.",
      "work_area": "DREAN GARANTIAS",
      "works_count": 82, "total_amount": 868835.00,
      "works": [
        { "work_order_id": 57942, "number": "OT-000123", "completed_at": "2025-06-18",
          "client_name": "PEREZ JUAN", "equipment": "LAVARROPAS DREAN",
          "model": "X", "serial_number": "PM0655", "technician": "ALLIONE ADRIAN",
          "amount": 19834.71 }
      ] }
  ],
  "totals": { "works_count": 91, "total_amount": 1045148.15 }
}
```

> **Junio 2025, medido sobre la base restaurada** (por `FechaLista` en el mes):
>
> | Bucket | OTs | Con empresa a liquidar | Costo |
> |---|---:|---:|---:|
> | Garantía (`Gt = 1`) | 91 | 91 | **1.045.148,15** |
> | Fuera de garantía (`Gt = 0`) | 59 | 32 | 1.429.099,19 |
> | **Total con empresa** | 123 | **123** | **1.675.486,90** |
> | Sin empresa (`CodCli = 0`) | 27 | — | 798.760,44 |
>
> Las 59 OTs fuera de garantía de junio 2025 son **32** con empresa (630.338,75 de costo
> repartido entre DREAN, BGH, WHIRLPOOL, FRIMETAL, TCL, NEBA, ORBIS, YAPAY, BAMBI, ELECTROLUX
> y LONGVIE) y **27** del área genérica sin empresa, que no se le liquidan a ninguna marca.
> **Por eso la respuesta cambia mucho según el criterio: 91 OTs / 1.045.148,15 contra
> 123 OTs / 1.675.486,90.**

### 5.4 Criterio de inclusión (definido, con la salvedad de §9)

**La regla** (§1.b.5): una OT entra al cierre si **su política pertenece a un área con
`CodCli <> 0`** — o sea, si hay una empresa a la cual liquidarle — y se le imputa a ese
cliente. El flag de garantía (`Gt`) **no** decide la inclusión: sólo categorize el trabajo
dentro del reporte.

```sql
-- borrador del reporte (destino)
SELECT wa.billing_customer_id,
       COUNT(*) AS works,
       SUM(wo.cost_total) AS total          -- campo a agregar (ver más abajo)
FROM work_orders wo
JOIN work_areas wa ON wa.id = wo.work_area_id
WHERE wo.company_id = :company_id
  AND wa.billing_customer_id IS NOT NULL        -- <-- la empresa a liquidar
  AND wo.completed_at >= :from AND wo.completed_at < :to
GROUP BY wa.billing_customer_id
```

**El importe.** El legacy lo tiene listo en `CS_Trabajos.CostoTotal`; el destino **no tiene
ese campo**. Dos caminos:

| Camino | Qué hace | Costo |
|---|---|---|
| **A — agregar `work_orders.cost_total`** (recomendado) | Una columna `DECIMAL(19,6) NOT NULL DEFAULT 0` que el importador llena con `CS_Trabajos.CostoTotal` | Trivial, y de paso queda guardado el costo de venta y el total presupuestado |
| **B — calcularlo siempre desde las líneas** | `SUM(work_order_parts.unit_cost × quantity)` en cada consulta del cierre | Cero schema nuevo, pero el cierre recalcula sobre 30 mil líneas cada vez y puede desfasar del legacy si el legacy redondea por OT |

Con A, además, `work_orders` gana también `sale_total` y `quoted_total`, que sí hacen falta
para mostrar la OT completa.

| Si el criterio es… | OTs (2020+) | Costo (2020+) | Nota |
|---|---:|---:|---|
| **A — sólo garantía** (`wa.warranty_type = 1`) | 2.853 | 25.356.252,43 | lo que hoy se conoce como "garantía" |
| **B — todo lo que tiene empresa** | 6.418 | 73.178.994,15 | incluye la rama `FUERA` de cada marca |

**Importante — la regla del legacy que hay que respetar al calcular el importe:** en garantía
de terceros **el precio de venta se infla** (`@Unitario = @Costo * (1 + @PorcUtil/100)`), por
eso `VentaTotal ≈ 2 × CostoTotal` en casi todas las OTs. Como la decisión 1.4 es liquidar el
**costo**, el importe a facturar a la marca es `CostoTotal`; si alguna vez se decide liquidar
la venta, el número se duplica y hay que avisarlo.

> Ojo con `CS_ImporteALiquidarOrden` (la función del legacy que se suponía el "importe a
> liquidar"): está **rota** — consulta la tabla `Partes`, que ya no existe (hoy es
> `CS_Partes`) — y además suma `Unitario` (precio de venta), no el costo. **No sirve como
> referencia**: el criterio real es el de `Areas.CodCli` + `CostoTotal`.

### 5.5 Cobertura de los datos para el cierre

Sobre las OTs en garantía por mes (2025-2026):

| Mes | OTs | Con `FacturaEmitida` | Con `Comprobante` | `Liquidada` |
|---|---:|---:|---:|---:|
| 2025-01 | 48 | 42 | 48 | 0 |
| 2025-06 | 91 | 80 | 91 | 0 |
| 2026-08 | 50 | 22 | 50 | 0 |
| 2026-09 | 52 | 0 | 52 | 0 |
| 2026-10 | 44 | 0 | 44 | 0 |

- `Liquidada` da **0** en garantía (porque el área tiene `Liquidar = 0`) ⇒ **el legacy no
  registra el cierre a marcas**. Por eso el sistema nuevo tiene que sumarlo.
- `FacturaEmitida` se corta a partir de 2026-09 (porque el número de factura pasó a
  `Comprobante`) ⇒ el reporte tiene que leer **las dos columnas**.

---

## 6. Fase 4 — Validación

| Chequeo | Origen | Destino | Tolerancia |
|---|---|---|---|
| Clientes | 14.730 | `customers` | 100 % (o la diferencia justificada por los descartes) |
| Equipos | 5.213 `(cliente, serie)` en 2020+ | `equipment` | 100 % |
| OTs | **9.316** (2020+) | `work_orders` | 100 % |
| OTs con técnico | 18.383 filas `Intervienen` | `work_order_technicians` | exacto |
| Líneas | 29.799 `CS_Partes` | `work_order_parts` | exacto |
| Suma de `VentaTotal` por mes | legacy | destino | diferencia 0 (o explicada por redondeo) |
| Suma de `CostoTotal` por mes | legacy | destino | diferencia 0 (o explicada por redondeo) |
| **Cierre de un mes** | recalculado desde el destino | vs. consulta al legacy | diferencia 0 |
| Clientes sin CUIT | 79 % | `document IS NULL` | — |

**El cuadre del cierre tiene que dar estos tres números fijos** (medidos sobre la base restaurada, corte
2020+ por `FechaAlta`), para comparar contra lo que devuelva el sistema nuevo:

| Concepto | OTs | Costo |
|---|---:|---:|
| Con empresa a liquidar (`CodCli <> 0`) | **6.418** | **73.178.994,15** |
| — de ellas, garantía (`Gt = 1`) | 2.853 | 25.356.252,43 |
| — de ellas, fuera de garantía de marca (`Gt = 0`) | 3.565 | 47.822.741,72 |
| Sin empresa (`CodCli = 0`) | 2.898 | 28.195.156,35 |
| **Total del corte** | **9.316** | **101.374.150,50** |

Además: **muestra de 20 registros por entidad**, lado a lado (legacy vs destino), y un
**cuadre por mes y por empresa a liquidar** que es el número que van a ver a fin de mes.

---

## 7. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | Mergear a `main` **despliega producción** (auto-deploy) | Trabajar en rama; deploy de staging a mano |
| 2 | La migración rompe producción si algo está mal | El backend corre `alembic upgrade head` al arrancar ⇒ migración **aditiva primero**, y probar en `staging-db` con `alembic downgrade` probado |
| 3 | Importar mal las marcas ⇒ el cierre mensual sale descuadrado | Pruebas de humo: 10 marcas + sus clientes, cerrar un mes y cuadrar contra el legacy |
| 4 | `Areas.Empresa` desactualizado ⇒ se liquida a la empresa equivocada | Usar `CodCli`, y un test que detecte los casos divergentes conocidos (§5.2) |
| 5 | Confundir `Liquidar` con "a quién se liquida" ⇒ se excluye la garantía entera | `Liquidar` **no** se usa como filtro del cierre (§1.b.2, §5.2). Test que falle si el filtro depende de `liquidate_mode` |
| 6 | Los 5.969 trabajos sin cliente (64 % del corte) ensucian el histórico | Emparejar por nombre; los que no, crear cliente "sin identificar" y marcarlos |
| 7 | `Equipo` con 13.327 valores distintos | Catálogo curado con los 60 más frecuentes + resto a "Otros" |
| 8 | El importe a liquidar no está claro | **Resuelto**: se liquida el costo (decisión 1.4). Falta elegir el camino A (`cost_total` en la OT) o B (recalcular desde líneas) → **recomendado A** |
| 9 | El importador no es idempotente | `work_order_import_rows.legacy_id` + re-ejecución segura |
| 10 | El legacy **nunca registró** el cierre a marcas ⇒ no hay contra qué validar | El primer cierre se valida contra una consulta equivalente escrita a mano sobre `CiberBase` (el SQL está en `backup/_work/ver_cierre.sql`) |

---

## 8. Orden de ataque sugerido

1. **Respuesta a las 4 decisiones de §9** — sin esto no se escribe la migración.
2. **Crear la empresa en staging** y verificar que el login funciona (§2).
3. **Migración de schema** sólo con `work_areas` (126 políticas) + las columnas de
   `work_orders` (`work_area_id`, `warranty_status`, `cost_total`, `sale_total`,
   `legacy_number`) + `work_order_parts` — lo mínimo para el cierre mensual (§3.1, §3.2).
4. **Importar clientes + marcas + equipos** de un mes suelto (**junio 2025**, el que ya está
   medido) y hacer el **cierre a mano** para validarlo contra el legacy.
5. **Recién ahí** el resto del schema y el importador completo.
6. **Cierre mensual** como endpoint + pantalla.
7. **Import histórico completo** (2020+ y, si se decide, 2001+).
8. **Bitácora** con los cuadres.

---

## 9. Las 4 decisiones que faltan (esperando tu respuesta)

Las contestadas están en §1. Estas cuatro cambian el resultado y **no puedo elegir por vos sin
confirmar**, porque el número que se ve a fin de mes depende de ellas:

| # | Decisión | Recomendación | Impacto si cambia |
|---|---|---|---|
| **9.1** | **Alcance del cierre**: ¿sólo garantía (`Gt = 1`) o también la rama `FUERA` de cada marca? | **Las dos** (todo lo que tiene empresa a liquidar) | 2.853 OTs / 25,4 M contra 6.418 OTs / 73,2 M en 2020+. Es la diferencia entre liquidar el 35 % o el 100 % del trabajo de marca |
| **9.2** | **Alladio** (`CodCli = 7634`): ¿se liquida como marca de fábrica o como *service oficial*? | Liquidarlo **sí**, pero con su propio criterio (tiene `Gt = 2` en "Garantía de Service") | 304 OTs / 174.081,12 en 2020+. Hoy su trabajo fuera de garantía no se le liquida (cae en el área genérica) |
| **9.3** | **Persona vs. empresa**: ¿CUIT válido + sufijo societario y **consolidar los 288 nombres repetidos**, o dejar cada sucursal como cliente aparte? | Consolidar | Define cuántos clientes quedan en `customers` (14.730 filas crudas contra ~1.300 reales) |
| **9.4** | **Mesas**: ¿maestro normalizado (`work_benches`) o texto libre? | Maestro normalizado | Permite medir carga por mesa después |

**Lo que este plan no cubre (a la espera, sin decisión pendiente):**

- **Comisiones de ventas de mostrador** (no están persistidas en el legacy ⇒ hay que
  recalcularlas: desarrollo, no importación).
- **Módulo de campo** del legacy (calendarios, zonas, recorridos, líneas por técnico): es de
  un móvil que no existe en el sistema nuevo.
- **Stock y depósitos** (`CK_StockxArticulo`, `CK_StockTecnico`): el stock del técnico
  está abandonado desde 2020-02-11.
- **Facturación electrónica / AFIP** del legacy (CAI, FCE MiPyme): el sistema nuevo no
  tiene emisión de comprobantes; sólo se importa el histórico de facturas.
- **Presupuestos** (`CG_Presupuestos_Tabla`): con la recomendación de §3.4 (sólo el total).
- **El histórico 2001-2019**: no entra en el primer corte (decisión 1.3).
