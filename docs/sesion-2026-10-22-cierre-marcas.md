# Sesión 2026-10-22 — CiberBrain: Fase 0 y Fase 1 (schema + cierre mensual a marcas)

Continuamos el plan de migración del legacy CiberBrain (CiberBase, SQL Server) a Vogel Gestión de
Servicios. El plan vive en `docs/plan-importacion-ciberbrain.md` y el análisis del legacy en
`docs/informe-migracion-ciberbrain.md`.

**Estado al terminar:** Fase 0 y Fase 1 cerradas, con la suite del backend en verde y el código
en un PR. La Fase 2 (importador) la está escribiendo **otra sesión en paralelo** sobre
`backend/scripts/import_cyberbrain/`; este PR **no** incluye esos archivos.

---

## 1. Fase 0 — la empresa en staging

La empresa no existía: en staging había seis (`Botz Blitz`, `Empresa Demo A`, `Empresa Demo B`,
`Empresa Smoke 37`, `Prueba Docs`, `Traid Walter`) y ninguna era la del legacy.

Se creó **Electrotecniref** (id=7, slug `electrotecniref`) con su propio administrador:

| Dato | Valor |
|---|---|
| Email | `admin@electrotecniref.com.ar` |
| Password | `64816AFA48B2F34E17!aZ` |
| Razón social | ELECTROTECNIREF S.A. |

El login del administrador funciona. Ojo con un detalle que parece un bug y no lo es: después de
iniciar sesión, `GET /companies/current` devuelve **409 "Active company required"** hasta que se
llama a `POST /api/v1/auth/select-company`. El token de login no trae empresa activa; hay que
elegirla.

## 2. Fase 1 — el schema

### Qué se agregó

| Modelo | Tabla | Para qué |
|---|---|---|
| `work_area.py` | `work_areas`, `work_benches`, `sellers`, `technicians` | Las "mesas de trabajo" del legacy (que **no** son sucursales) y el maestro de marcas |
| `work_order_part.py` | `work_order_parts`, `work_order_technicians`, `work_order_part_commissions` | Las líneas de repuestos/servicio con los cuatro cubos de comisión |
| `warranty_settlement.py` | `warranty_settlements`, `warranty_settlement_orders` | El cierre mensual a marcas |
| `invoice.py` | `invoices` | Factura: fecha y número |

Y columnas nuevas en `work_orders` (`legacy_id`, `legacy_number`, `work_area_id`,
`work_bench_id`, `warranty_status`, `cost_total`, `sale_total`, `quoted_total`,
`legacy_invoice_number`) y en `customers` (`seller_id`).

Migraciones: `20261022_0024_cyberbrain_marca_garantia` y `20261022_0025_permisos_cierre_marcas`.

### El endpoint del cierre

`backend/app/api/v1/warranty_settlements.py` + `backend/app/services/warranty_settlements.py`:

- `GET /api/v1/warranty-settlements?period=2025-06` — el reporte del mes.
- `GET /api/v1/warranty-settlements/registros` — los cierres ya registrados.
- `POST /api/v1/warranty-settlements/generate` — calcula y registra el periodo.
- `POST /api/v1/warranty-settlements/{id}/issue` — emite (congela el periodo).
- `POST /api/v1/warranty-settlements/{id}/settle` — liquida, con número de factura.

Dos permisos nuevos: `warranty_settlements.view` y `warranty_settlements.manage`.

---

## 3. La regla de oro, escrita en tests

El legacy no tiene cierre a marcas: se hacía a mano y no quedaba registrado, así que **no hay un
contra contra el cual validar**. Por eso la regla quedó escrita en `backend/tests/test_cierre_marcas.py`
(18 tests), no solo en la documentación.

**La regla:** entra al cierre toda OT cuya política pertenezca a un área con empresa a liquidar
(`work_areas.billing_customer_id` no nulo), y se le imputa a ese cliente.

Tres errores que los tests cierran:

1. **Confundir `Liquidar` con "a quién se liquida".** `Areas.Liquidar` es el ciclo de vida de la
   OT (0/3 = liquidación manual, 1 = automática, 2 = nunca), **no la deuda**. En las áreas de marca
   vale 0. Si el cierre filtrara por ahí, se excluiría justo la garantía, que es lo que hay que
   liquidar.
2. **Excluir el trabajo fuera de garantía.** La rama `FUERA` de cada marca también se le factura a
   la marca. En el corte 2020+ son 3.565 OTs y 47,8 M: más de la mitad de la plata.
3. **Liquidar el precio de venta en vez del costo.** En garantía de terceros el legacy infla el
   precio (`@Unitario = @Costo * (1 + @PorcUtil/100)`), así que la venta sale aproximadamente el
   doble.

Además: la OT es de "PEREZ JUAN" y se liquida a "DREAN S.A." (el `CodCli` del área). El cliente
final no es a quien se liquida.

### Los tests muerden (probado saboteando)

Se saboteó el servicio tres veces, una por error, y se comprobó que los tests lo detectan:

| Saboteo | Resultado |
|---|---|
| Filtrar por `Liquidar` en vez de por la empresa a liquidar | **DETECTADO** — 2 tests en rojo |
| Liquidar solo la garantía (dejar fuera la rama `FUERA`) | **DETECTADO** — 1 test en rojo |
| Liquidar `sale_total` en vez de `cost_total` | **DETECTADO** — 13 tests en rojo |

Un test que no se rompe con el código saboteado no protege nada.

---

## 4. Tres bugs que aparecieron por el camino

### 4.1 La migración 0024 reventaba la suite en SQLite

`NotImplementedError: No support for ALTER of constraints in SQLite dialect`. El problema es
`op.add_column` + `op.create_foreign_key` sueltos sobre tablas existentes: SQLite no soporta
alterar constraints. La solución es el patrón que ya usaban las migraciones 0004 y 0006 del repo:
`op.batch_alter_table`, que en SQLite recrea la tabla y en MySQL emite los ALTER de siempre.

Esto no era cosmético: **la suite entera estaba en rojo** (6 tests de migraciones), porque todos
corren `alembic upgrade head`.

### 4.2 `HEAD_REVISION` hardcodeado en los tests de migraciones

`HEAD_REVISION = "20261004_0023"`: con cada migración nueva, los tests de migraciones fallaban con
un error que decía `assert '20261022_0025' == '20261004_0023'` — que no dice nada del problema
real. Pasó dos veces. Ahora se deriva de los scripts con `ScriptDirectory.get_current_head()`.

### 4.3 Un número mal en el plan, que iba a romper el cuadre

El plan decía que las 32 OTs fuera de garantía de junio 2025 con empresa a liquidar sumaban
**1.430.338,75** de costo. No puede ser: el total con empresa del mes es 1.675.486,90 y la
garantía sola son 1.045.148,15, así que la diferencia es **630.338,75**. Y con eso cuadra la otra
cuenta: 630.338,75 (las 32 con empresa) + 798.760,44 (las 27 sin empresa) = 1.429.099,19, que es
lo que dice la tabla. El error estaba en la prosa, no en la tabla. Corregido.

Sirve como recordatorio de que el cuadre de junio 2025 tiene **dos** respuestas posibles y hay que
saber cuál se está mirando: 91 OTs / 1.045.148,15 (solo garantía) contra 123 OTs / 1.675.486,90
(todo lo que tiene empresa a liquidar).

---

## 5. Verificado contra la API real de staging

Staging se desplegó **con la rama, antes de mergear**, para probar la migración 0024 contra
MySQL real sin tocar producción. Recién después se mergeó.

Como el importador todavía no corrió, se sembró el mínimo en la base de la empresa
Electrotecniref (id=7): la marca DREAN S.A., el cliente final PEREZ JUAN, un equipo, **dos
áreas** (una de garantía y una fuera de garantía, las dos con la marca como empresa a liquidar)
y tres OTs: dos de junio 2025 y una de julio 2025.

El reporte de junio 2025, contra la API real:

```
empresa a liquidar : DREAN S.A. (id=2047)
total obras        : 2
importe total      : 400.000000   <- COSTO, no la venta
en garantia        : 1 obras por 100.000000
fuera de garantia  : 1 obras por 300.000000
   OT 1 | 2025-06-18 | area=DREAN GARANTIAS | garantia=1 | cliente=PEREZ JUAN | importe=100
   OT 2 | 2025-06-20 | area=DREAN FUERA DE GARANTIA | garantia=0 | cliente=PEREZ JUAN | importe=300
```

Lo que eso demuestra, contra MySQL y no contra el código:

- **La empresa a liquidar es DREAN S.A., no PEREZ JUAN.** PEREZ JUAN es el cliente final.
- **Se liquidan 400, que es el costo.** La venta de esas dos OTs suma 850.
- **La OT de julio queda fuera**: 1 obra, 999, en el reporte de julio.
- **Los dos buckets se separan**: 100 en garantía, 300 fuera de garantía.

El ciclo completo, en vivo:

| Paso | Resultado |
|---|---|
| `GET /warranty-settlements?period=2025-06` | 200, 1 empresa, 2 obras, 400 |
| `POST /warranty-settlements/generate` | 200, el reporte |
| `GET /warranty-settlements/registros` | 1 registro: id=1, 2025-06, `draft`, 400, DREAN S.A. |
| `POST /{id}/issue` | `issued` |
| `POST /{id}/settle` | `settled` |
| `POST /generate` de nuevo | 409: *"El cierre de DREAN S.A. para 2025-06 esta 'settled' y no se puede regenerar"* |
| `GET ?period=junio-2025` | 422, el periodo tiene que ser `AAAA-MM` |

Dos cosas que se aprendieron probing:

- **`GET /` devuelve 401 aunque la ruta no exista**: el control de acceso corre antes del
  ruteo. Un 401 no prueba que la ruta exista; un 404 sí prueba que no existe. Para probar que
  una ruta nueva está desplegada hay que mandar un token.
- **`POST /generate` devuelve el reporte, no el registro.** El id del cierre hay que sacarlo de
  `GET /registros`.

---

## 6. Decisiones que conviene no olvidar

- **El importe que se liquida es el costo.** El precio de venta de la garantía de terceros está
  inflado por el legacy; el costo es el número que se le factura a la marca.
- **`Liquidar` no es "a quién se liquida".** Si alguna vez hay que tocar el filtro del cierre, que
  sea por `billing_customer_id`.
- **La marca se liquida con el mismo ritmo que la garantía**, en la misma planilla mensual.
- **El cierre congela al emitirse.** Emitido no se regenera: si se pudiera, los números del mes
  cambiarían sin que nadie lo note.
- **El importador no es de esta sesión.** Los archivos de `backend/scripts/import_cyberbrain/` los
  está escribiendo otra sesión en paralelo sobre el mismo repo. Este PR no los toca.

---

## 7. Pendientes

- **Fase 2:** importador (otra sesión). Falta el cuadre contra el legacy: junio 2025 da 91 OTs de
  garantía por 1.045.148,15 (y 123 OTs / 1.675.486,90 contando las que no son de marca).
- **Fase 3:** pantalla del cierre mensual. Hoy solo hay endpoint.
- **Fase 4:** la importación histórica completa.
- **Cierre de la garantía con `warranty_status`:** la garantía del legacy viene de la **política**
  (`Aux_PoliticasxArea.TipoTrabajo`), no de un flag de la OT. Copiarlo 1:1 daría datos incorrectos
  (riesgo 4 del informe, §8.6).
- **Comisiones:** el legacy **no persiste** la comisión de ventas de mostrador
  (`CC_ComisionesVentas` se calcula al vuelo). Si el sistema nuevo la va a liquidar, hay que
  **recalcularla** con la fórmula original y decidir dónde se guarda.
- **Las OTs sin cliente vinculado (9.151)** hay que emparejarlas por nombre o creando el cliente.
- **Staging:** la empresa Electrotecniref quedó creada y con `ai.enabled` sin tocar.
