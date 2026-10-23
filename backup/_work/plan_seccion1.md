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

