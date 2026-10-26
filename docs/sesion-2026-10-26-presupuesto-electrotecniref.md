# Sesión 2026-10-26 — El presupuesto de Vogel Gestión de Servicios para Electrotecniref

Objetivo de la sesión: armar la propuesta económica de un **abono mensual** para
Electrotecniref y dejar por escrito de dónde sale cada número.

**Resultado:**
- `docs/propuesta-abono-mensual-electrotecniref.docx` — la propuesta lista para enviar.
- Este documento — la bitácora interna: razonamiento, fuentes y límites.

**Revisión 3 (26/10/2026, cierre del día):** se aplicó el número final del
usuario (ARS 500.000 en el mes 1 + ARS 300.000/mes desde el mes 2) a la
propuesta y a esta bitácora. En el camino se recalcularon las bases medidas
sobre el dump y se encontró un error de dígito (§3.3).

**Números finales:**

| Concepto | Importe |
|---|---:|
| Mes 1: puesta en marcha + primer mes de servicio, en un solo pago | **ARS 500.000** |
| Abono mensual base (desde el mes 2) | **ARS 300.000 / mes** |
| Precio de lista del abono | ARS 300.000 / mes (sin salto por antigüedad) |
| Cuota de IA incluida | USD 30 / mes (~9.000 turnos) |
| Mensajes de WhatsApp incluidos | 400 / mes |
| Total del primer año (12 meses) | ARS 3.800.000 |
| Recurrente anual, del año 2 en adelante | ARS 3.600.000 |

> **El número se corrigió dos veces en la sesión, y la última fue del usuario.**
> La primera versión propuso ARS 650.000/mes + ARS 850.000 de puesta en marcha:
> el precio mensual estaba mal calculado (§3.1) y se corrigió a ARS 30.000/mes.
> Después el usuario lo corrigió a mano: *"me equivoque, era trescientos mil
> pesos y quinientos mil por única vez, y los 300 a partir del mes finalizado;
> así el primer mes se cobra 500 y luego 300 cada mes"*. Los números de
> arriba son los que van firmados: el ancla de §3 se ajustó **alrededor** del
> número del usuario, no al revés.
>
> Con 300.000/mes el precio queda en **2,93% de la facturación mensual del
> taller** (§3.1), dentro de la banda de mercado, y vuelve a financiarse todo
> lo que a 30.000 no se sostenía: el SLA de 4/8 horas, la cuota de IA y el
> cupo de WhatsApp (§3.4).

---

## 1. La decisión de encuadre

La pregunta era "cómo plantear un abono mensual". Lo que se decidió:

| Decisión | Elección | Por qué |
|---|---|---|
| Moneda del abono base | **ARS, con ajuste por IPC anual** | El hosting y el soporte se pagan en pesos. Fijar el abono en una moneda dura congela el margen contra la inflación local. |
| Moneda de los adicionales | **USD** | El costo real de la IA está medido en dólares y se factura aparte. |
| Unidad de cobro | **Por empresa (tenant)** | El sistema ya es multiempresa y el tenant es el que activa módulos. No se cobra por usuario: obligaría a auditar licencias y castiga al cliente que activa gente. |
| Puesta en marcha | **Única vez, cobrada con el primer mes** | Es trabajo real y por una sola vez, no un abono recurrente. El mes 1 se factura un solo pago de ARS 500.000 que la incluye, y del mes 2 en adelante queda solo el abono mensual. |

**Lo que NO se hizo, y por qué:** un precio por usuario o por orden de trabajo.
El volumen real ya está medido y es estable (ver §2), así que un abono por
tenant con límites de volumen ancho y un excedente medido cubre el caso sin
meter un mecanismo de medición que el sistema no tiene hoy.

**La excepción es el cupo de WhatsApp:** es el único incluido que sí necesita
un contador que hoy no existe, porque sin él no se puede saber si el cliente
se pasó de los 400 mensajes ni cuánto facturarle el excedente (§4.1). Está
anotado como pendiente antes de la firma.

---

## 2. De dónde salen los números

Todo lo que sigue sale de **medir el dataset real**, no de estimar. La fuente
primaria es el dump de staging (`backup/_work/dump_local_cierre.sql`, 39 tablas,
el mismo que se aplicó a la base de staging).

### 2.1 Volumen de órdenes de trabajo

Parseando las 9.316 filas de `work_orders` del dump, agrupando por mes de
`received_at`:

| Año | OTs |
|---|---:|
| 2020 | 1.294 |
| 2021 | 1.161 |
| 2022 | 1.366 |
| 2023 | 1.207 |
| 2024 | 1.474 |
| 2025 | 1.617 |
| 2026 (hasta el 21/10) | 1.197 |

- Mediana mensual (todo el histórico): **114 OTs**. Pico: **181** (julio 2025).
- Promedio 2025 → sept 2026 (21 meses completos): **130 OTs**. Promedio 2026
  (9 meses completos): **124**.
- Total del legacy: **56.619 trabajos** en 25 años (`docs/informe-migracion-ciberbrain.md`).

> El dump se tomó el **21/10/2026**: **octubre de 2026 está incompleto** (69
> obras liquidables contra 74–126 de los meses previos, y 84 OTs recibidas
> contra 92–150). Por eso los promedios que se publican excluyen ese mes:
> contarlo baja artificialmente el promedio mensual. Ver §3.3.

### 2.2 Lo que se liquida contra las marcas

Criterio **idéntico al del código** (`backend/app/services/warranty_settlements.py:119-170`):
entra la OT que tiene `work_areas.billing_customer_id` no nulo, el importe es
`work_orders.cost_total` (el costo, no la venta) y el período sale de
`completed_at`.

| Dato | Valor |
|---|---:|
| OTs liquidables en el dataset | 6.318 |
| Costo liquidado total | ARS 73.026.102 |
| Promedio por obra | ARS 11.558 |
| **Promedio mensual (todo el período)** | **ARS 890.562** |
| **Promedio mensual 2026 (9 meses completos, ene-sep)** | **ARS 2.831.922** |
| Promedio mensual 2026 (incluyendo oct, mes a medias) | ARS 2.610.309 |

> **Error propio corregido en esta revisión:** esta tabla decía
> "ARS 2.631.921", que era **2.831.921** con un dígito mal escrito (6 en vez
> de 8). El valor correcto es el promedio de los nueve meses completos de
> 2026: **ARS 2.831.922**. Como el documento al cliente dice "alrededor de
> ARS 2,8 millones", el número correcto es el que se publica. Ver §3.3.

### 2.3 La validación que da confianza en el número

El parser se validó contra un dato **conocido y externo**: el cierre de junio
2025, que el equipo ya había verificado contra el legacy.

```
junio 2025 -> 123 obras, costo 1.675.486,90
esperado (docs/sesion-2026-10-23-staging-ciberbrain.md): 123 obras / 1.675.486,90
```

**Coincide al centavo.** Si el criterio de inclusión o el importe estuvieran
mal, ese número no cerraría. Es la razón por la que las cifras de la propuesta
son defendibles.

### 2.4 Otros números verificados

| Dato | Valor | Origen |
|---|---:|---|
| Áreas de trabajo (marcas) | 126 | `work_areas` |
| Áreas con empresa a liquidar | 116 | `work_areas.billing_customer_id` |
| Marcas distintas a liquidar | 34 | clientes con `billing_customer_id` |
| Usuarios de Electrotecniref | 46 | `company_users` (company_id=3) |
| Técnicos activos | 11 | `docs/informe-migracion-ciberbrain.md` |
| Intervinientes con comisiones | 18.383 | `work_order_technicians` |
| Clientes | 17.565 | `customers` |

---

## 3. Cómo se calculó el precio

> **Corrección (26/10/2026, segunda revisión).** La primera versión de esta
> bitácora afirmaba que un abono de ARS 650.000 era "del orden del 0,8%–1,5%
> de la liquidación mensual". **Eso estaba mal: es 22,95%** (24,9% contra la
> base que se publicaba entonces; §3.3 corrige esa base). El error fue mío
> (dividí mal al mezclar la base de cálculo). El precio se recalculó contra
> las dos bases correctas y se corrigió la propuesta. Ver §3.1.

El abono se ancla contra **el valor que el sistema mueve**, no contra un
arbitrio de mercado. Y hay **dos** bases posibles, y no dan lo mismo:

| Base | Promedio mensual 2026 | Qué es |
|---|---:|---|
| **Liquidación a marcas** (`cost_total` de las OTs con empresa a liquidar) | **ARS 2.831.922** | Lo que las marcas le pagan al taller. Es lo que el sistema *produce*. |
| **Facturación del taller** (`sale_total` de todas las OTs) | **ARS 10.237.942** | Lo que el taller le factura a sus clientes. Incluye el trabajo fuera de garantía. |

Los dos promedios son sobre los **nueve meses completos de 2026** (enero a
septiembre). Si se incluye el mes a medias de octubre, dan ARS 2.610.309 y
ARS 9.519.548, y el abono se ve un 0,2 punto más caro (§3.3).

Anualizado, el taller factura ~**ARS 123 millones por año** (2026).

### 3.1 El precio como porcentaje de cada base

| Abono mensual | % de la liquidación | % de la facturación | Horas de soporte que financia* |
|---|---:|---:|---:|
| ARS 30.000 | 1,06% | **0,29%** | 1 a 2 h/mes |
| ARS 120.000 | 4,24% | 1,17% | 4 a 8 h/mes |
| ARS 200.000 | 7,06% | 1,95% | 6,7 a 13,3 h/mes |
| **ARS 300.000** | **10,59%** | **2,93%** | **10 a 20 h/mes** |
| ARS 650.000 | 22,95% | 6,35% | 21,7 a 43,3 h/mes |

\* A 15.000–30.000 ARS/hora. Es un supuesto, no un dato del repo: hay que
ajustarlo al costo real de la hora de Vogel.

**La lectura honesta:** contra la facturación del taller, el software de
gestión en una pyme de servicios se ubica en el **1%–3%** (IDC, vía
ZENIA/cleverals). **ARS 300.000 cae en esa banda, en el techo**: 2,93% sobre
los meses completos, 3,15% si se cuenta el mes de octubre a medias. Por eso
el documento al cliente dice "cerca del 3%" y no un decimal exacto. ARS
650.000 superaba la banda por más del doble; ARS 30.000 quedaba por debajo
del piso.

### 3.2 El número que deja el error

El primer error de la bitácora (la base mal calculada) fue el que llevó a
proponer ARS 650.000. Recalculado contra las bases correctas, **el mismo
ancla que yo había anunciado —0,8%–1,5% de la liquidación— da
aproximadamente ARS 30.000**, no ARS 650.000. El número que propuso el
usuario es el que sale de la regla que la propia bitácora enunciaba.

Es un recordatorio de por qué las cifras de acá se miden y no se estiman: un
porcentaje mal calculado se ve igual de convincente que uno bien calculado.

### 3.3 La ventana temporal: octubre 2026 está incompleto

El dump se tomó el **21/10/2026**. Todo lo que se publica como "promedio
mensual 2026" se calcula sobre **enero a septiembre**, los nueve meses
completos. Incluir octubre baja el promedio porque el mes está a medias:

| Mes | OTs liquidables | Costo liquidado | OTs recibidas | Venta |
|---|---:|---:|---:|---:|
| 2026-01 | 126 | 3.590.461,09 | 132 | 9.288.471,66 |
| 2026-02 | 85 | 2.204.576,46 | 127 | 8.028.819,55 |
| 2026-03 | 74 | 1.762.142,13 | 115 | 7.802.038,14 |
| 2026-04 | 114 | 3.293.324,40 | 118 | 12.578.258,78 |
| 2026-05 | 90 | 2.791.164,12 | 107 | 9.688.691,33 |
| 2026-06 | 79 | 2.052.680,12 | 122 | 12.682.454,38 |
| 2026-07 | 123 | 3.881.532,44 | 150 | 13.374.889,73 |
| 2026-08 | 93 | 3.258.992,24 | 92 | 7.818.029,53 |
| 2026-09 | 104 | 2.652.421,63 | 150 | 10.879.826,60 |
| **Promedio ene-sep** | **99** | **2.831.921,63** | **124** | **10.237.942,19** |
| 2026-10 *(incompleto)* | 69 | 615.799,63 | 84 | 3.054.000,02 |
| Promedio con oct incluido | 96 | 2.610.309,43 | 118 | 9.519.547,97 |

**Dos errores que salieron de acá, y cómo se detectaron:**

1. **Un dígito mal escrito.** §2.2 decía "ARS 2.631.921"; el valor medido es
   **ARS 2.831.922**. No se detectó leyendo: se detectó al recalcular la
   serie mes a mes desde el dump y ver que el número no cerraba con ninguno
   de los promedios posibles.
2. **Un mes a medias.** Al recalcular la serie apareció que octubre 2026
   tenía 69 obras liquidables contra 74–126 de los meses previos. El dump es
   del 21/10: el mes no estaba terminado.

**Y un casi-error propio.** Al corregir la cifra de la liquidación, cambié en
el documento "alrededor de ARS 2,8 millones" por "2,6 millones", tomando la
base mal calculada. Al volver a correr el cálculo sobre los meses completos
se vio que **2,8 millones era el número correcto** y que el 2,6 era el
promedio con el mes a medias. El documento volvió a 2,8 millones antes de
mandarse.

> Regla que sale de esto: **cuando el número publicado y el número recalculado
> no coinciden, no se elige uno: se busca la causa.** En este caso la causa
> era la ventana temporal, no el cálculo.


### Los límites incluidos

Calibrados con margen sobre el uso real, porque el excedente **debe ser la
excepción**:

| Concepto | Incluido | Uso real | Excedente |
|---|---:|---:|---:|
| Usuarios activos | 75 | 46 | ARS 4.000/usuario/mes |
| OTs por mes | 250 | 130 (pico 181) | ARS 1.200/OT |
| Áreas de trabajo | 150 | 126 | sin costo |
| Empresas a liquidar | sin límite | 34 | — |
| Mensajes de WhatsApp | 400 | 248 (pico 362) | a costo de Meta |
| Consumo de IA | USD 30/mes (~9.000 turnos) | 110 a 440 turnos | al costo + 30% |

Las áreas van 126 de 150 porque **es el número que ya está cargado** y no va a
crecer: son las marcas con las que se trabaja. Subir ese límite no genera
conversaciones comerciales.

### Puesta en marcha: ARS 500.000

El número es **menor** que el de una implementación desde cero, y a propósito:
la migración del histórico (el 80% del trabajo) **ya está hecha y verificada**.
Lo que se cobra es el corte a producción, los 46 usuarios individuales, la
configuración, dos jornadas de capacitación, la habilitación de módulos y 30
días de garantía de arranque.

**El mes 1 se factura un solo pago de ARS 500.000**, que incluye la puesta en
marcha **y el primer mes de servicio**. Del mes 2 en adelante son
ARS 300.000 por mes. Primer año: ARS 3.800.000 (500.000 + 11 × 300.000);
recurrente del año 2 en adelante: ARS 3.600.000.

### El abono mensual: ARS 300.000

Es el número que fijó el usuario, y contra la base correcta da **2,93% de la
facturación mensual del taller** (§3.1): en el techo de la banda de 1%–3% en
la que se ubica el software de gestión en empresas de servicios de tamaño
comparable.

Contra la liquidación a marcas es 10,59%: no es un número que se pueda
presentar como "el sistema produce esto y te lo cobra", y no se presenta
como tal. La facturación total es la base correcta para comparar contra el
benchmark, porque es lo que el taller factura a sus clientes.

Lo que cambia con este precio, contra lo que se había armado para 30.000:

| Punto | Con ARS 30.000 | Con ARS 300.000 | Por qué |
|---|---|---|---|
| Soporte | 1 a 2 h/mes, sin SLA de 4/8 h | **10 a 20 h/mes, con SLA de 4/8 h** | A 15.000–30.000 ARS/h, el SLA de incidente crítico en 4 h hábiles deja de ser una promesa sin respaldo. |
| Cuota de IA | USD 10 (5,2% del abono) | **USD 30 (15,5% del abono, ~9.000 turnos)** | El uso real es de céntimos (220 turnos = USD 0,73). La cuota es un **techo**, no un gasto: cuanto más alto, menos riesgo de que al cliente se le corte el asistente y menos exposición para nosotros. |
| WhatsApp | No incluido, a consumo real | **400 mensajes/mes incluidos** | Ver §4.1: 400 × ARS 37,68 = ARS 15.072, el 5,0% del abono. Cubre el pico histórico (362). |
| Precio de lista | 30.000 de lanzamiento, 120.000 al mes 13 | **300.000 de lista, sin salto por antigüedad** | El precio único evita tener que defender un salto a los 12 meses y deja margen para el ajuste por IPC. |
| SLA | Se revisaba al mes 13 | **Se mantiene en toda la vigencia** | El abono incluye el soporte que el SLA requiere. |

### 3.4 Lo que hay que confirmar antes de enviar

- [x] **El número**: lo fijó el usuario. Base, estructura y alcance se
      ajustaron alrededor.
- [ ] **La bonificación anual que agregué**: 12 meses de abono por adelantado
      con 2 meses sin cargo (ARS 3.000.000 por año). Es una propuesta mía,
      no un número que haya dado el usuario. Es una sola celda de la tabla de
      condiciones comerciales: si no va, se borra y listo.
- [ ] **El costo real de la hora de soporte de Vogel** (§8). Con 300.000 el
      margen es amplio (10–20 h/mes), así que deja de ser bloqueante, pero
      conviene tenerlo medido.

---

## 4. Lo que el sistema ya sabe medir (y por qué los excedentes son creíbles)

Esto es lo que hace que "se factura al consumo medido" no sea una frase de
marketing:

| Concepto | Cómo se mide hoy | Dónde |
|---|---|---|
| Consumo de IA | Una fila por pedido al proveedor, con tokens y costo estimado. **Se escribe también cuando la llamada falla**, para que el acumulado no mienta cuando el proveedor está caído. | `backend/app/models/ai_usage.py`, `backend/app/services/ai/usage.py` |
| Período de IA | Corte mensual en UTC, con historial de 12 meses para facturar | `usage.py:25-37`, `usage.py:176-215` |
| Cuota de IA | Techo por empresa, en USD, con tope de pedidos | `ai.monthly_quota_usd`, `ai.monthly_request_limit` |
| Quién puede tocar la cuota | **Nadie de la empresa**: los parámetros son de plataforma, `editable=false`, y se cambian por un endpoint superadmin con nombre propio | `backend/app/core/parameter_catalog.py:24-49`, `backend/app/api/v1/companies.py:389-537` |
| Volumen de OTs | Se cuenta por mes sobre `work_orders.received_at` | el mismo criterio que usa el tablero |
| Marcas a liquidar | `work_areas.billing_customer_id` | `warranty_settlements.py:140-143` |

Es decir: **la mayor parte de la propuesta comercial ya está instrumentada en
el código**. La cuota de IA por empresa con medición mensual y control de
plataforma es exactamente el mecanismo de un abono por consumo. La excepción
es el contador de WhatsApp (§4.1).

### Lo que NO se puede medir hoy, y por eso no se factura así

| Concepto | Estado real | Decisión |
|---|---|---|
| **Conversaciones de WhatsApp** | El sistema registra los envíos (`work_order_notifications` con `provider_message_id` y estado) pero **no cuenta ni costea mensajes**. | **Cupo de 400/mes incluido** (§4.1: ARS 15.072/mes, 5,0% del abono). **Antes hay que implementar el conteo**, porque sin contador el cupo no se puede cumplir ni controlar. |
| **Almacenamiento** | Hay límite por archivo (`storage_max_file_mb: 25`) pero no un total medido en GB. | 20 GB incluidos, a ajustar. |
| **Exportación de datos** | **No existe exportación.** Sólo import `.xlsx` y descarga de documentos. | Es compromiso de puesta en marcha, ver §5. |

### 4.1 El costo de WhatsApp: lo que rompe un abono de 30.000 y lo que financia uno de 300.000

Meta factura **por mensaje entregado**, no por conversación, y su rate card
para Argentina (vigente desde el 1/10/2026) es:

| Categoría | Precio | Nota |
|---|---:|---|
| Servicio (responde a un cliente que te escribió, dentro de 24 h) | **ARS 37,68** | Las primeras 1.000 respuestas al mes por número son gratis |
| Utilidad (aviso de estado de una OT) | **ARS 37,68** | **Siempre se cobra**, también dentro de una ventana de servicio abierta |
| Marketing | ARS 89,56 | — |

Un aviso de estado de OT es categoría **utilidad**: se cobra siempre.

El taller tiene ~124 OTs/mes. Con 2 avisos por OT (recepción y entrega) son
~248 mensajes/mes, y en el pico histórico (181 OTs) 362:

```
248 mensajes × ARS 37,68 = ARS 9.345/mes
362 mensajes × ARS 37,68 = ARS 13.640/mes   (pico)
400 mensajes × ARS 37,68 = ARS 15.072/mes   (cupo incluido)
```

**Con un abono de 30.000 eso era casi un tercio del abono y no se podía
incluir nada.** Con 300.000, un cupo de 400 mensajes/mes son el **5,0% del
abono** y cubre el pico histórico con margen. Por eso la propuesta incluye el
cupo.

El límite de esta versión es que **el sistema todavía no cuenta los
mensajes**: registra los envíos (`work_order_notifications` con
`provider_message_id` y estado) pero no lleva un contador ni costea. Para
prometer 400 incluidos hay que **implementar el conteo antes de la firma**
(§7). Sin ese contador, el cupo es una promesa que no se puede cumplir ni
controlar.

La salida más limpia para el cliente: que Electrotecniref use **su propia
instancia** de WhatsApp (el sistema ya lo soporta:
`whatsapp_api_key_encrypted` por empresa, con `whatsapp_use_platform_key`
como opt-in a la key de plataforma). Si el taller tiene su número, la factura
de Meta le llega a él, ese consumo no se descuenta del cupo y a Vogel no le
entra ese costo por el medio. El documento dice las dos cosas: el cupo
incluido y la alternativa.

---

## 5. Lo que se promete y lo que hay que hacer antes de firmar

Esta es la parte que importa: **la propuesta promete tres cosas que el sistema
todavía no tiene** (respaldo, exportación y el contador de WhatsApp). Hay que
cerrarlas antes de que el cliente las firme como compromiso.

### 5.1 Respaldo automático diario — NO ESTÁ CONFIGURADO

Verificado contra la API de Coolify: `GET /databases/{uuid}/backups` devuelve
**lista vacía** en las dos bases (staging `diamcot1wyytezyasugd5biv` y
producción `9m3hezemwa4nhdric1alwtmf`). **No hay ningún respaldo programado.**

Sin embargo la propuesta dice "respaldo automático diario, RPO 24 h, RTO 8 h,
prueba de restauración mensual". Eso es un compromiso con fecha y forma. Hay
que:

1. Configurar el respaldo diario en Coolify para las dos bases.
2. **Probar una restauración de verdad** y medir cuánto tarda (el RTO de 8 h
   tiene que salir de la medición, no de la intuición).
3. Recién ahí se puede dar por cumplido el compromiso.

> Nota: `mysql:8` en producción es una etiqueta móvil — la misma causa raíz del
> incidente de staging del 23/10 (`docs/sesion-2026-10-23-staging-ciberbrain.md` §4).
> Conviene fijarla a `8.4.13` antes de tocar respaldos.

### 5.2 Exportación de datos en formatos abiertos — NO EXISTE

Hoy sólo hay import `.xlsx` (`work_order_imports.py`) y descarga de documentos
(`equipment_documents.py:213`). **No hay endpoint ni script de exportación.**

La propuesta lo presenta como parte de la puesta en marcha, y la condición de
baja promete que el cliente conserva sus datos. Eso es lo correcto
comercialmente y también lo que un cliente va a preguntar primero ("si me voy,
¿me llevo la información?"). Hay que implementarlo antes de la firma.

**Alternativa si no llegara a implementarse:** ofrecer el dump de la base (una
copia MySQL) como formato de exportación. Es menos usable que un CSV, pero es
real hoy y cumple la promesa.

### 5.3 El historial en producción — la base de producción está vacía

Verificado en la API de Coolify, las dos apps apuntan a **bases distintas**:

```
staging-backend    -> diamcot1wyytezyasugd5biv:3306/vogel_gestion_servicios   (con los datos)
production-backend -> 9m3hezemwa4nhdric1alwtmf:3306/default                    (vacía)
```

Es decir: **todo el histórico de Electrotecniref vive hoy en staging.** El
"corte a producción" de la propuesta no es un formality; es mover 9.316 OTs,
17.565 clientes y 126 áreas a la base de producción y volver a verificar un
cierre contra el legacy.

### 5.4 Estado de los módulos al momento de la propuesta

| Módulo | Staging | Producción | Qué falta |
|---|---|---|---|
| Catálogo de repuestos (Flexxus) | **Habilitado** para Electrotecniref | **Apagado** | Decidir la lista de precios (1 = `PRECIOVENTA1` con margen, o `PRECIOCOMPRA` sin margen). Es una decisión comercial, y el paso 2 de la propuesta la pide explícitamente al cliente. |
| Asistente con IA | Apagado | Apagado | Se habilita por plataforma con `PUT /companies/{id}/ai` + cuota (**USD 30/mes**, el valor que propone la propuesta). Ya está instrumentado. |
| WhatsApp | Habilitado | Habilitado | Habilitar la instancia por empresa con su propia key, o usar la key de plataforma (`whatsapp_use_platform_key`). |
| Cierre a marcas | Validado al centavo | Validado al centavo | — |

### 5.5 El staging no está en `main`

`staging-backend` corre la rama `feat/finalizacion-tecnica-cierre` (commit
`d39fe5b`, un commit adelante de `main`), y había un deploy **in_progress**
al momento de esta sesión. `production-backend` corre `main` en `HEAD` y está
`running:healthy` (`/health` → `{"status":"ok","commit":"52fa89a"}`).

Antes de la puesta en marcha hay que **restaurar staging a `main`**, como ya
queda anotado en los pendientes de la sesión del 23/10.

---

## 6. Una ambigüedad sobre el ERP de repuestos

La documentación llama al ERP Flexxus "el ERP de Suevos" y dice que es "de un
solo cliente", pero:

- El usuario configurado es `ELECTROTR` y la base es `DB-ETR.gdb`
  (`backend/app/core/config.py:60-65`).
- El módulo está **habilitado únicamente para Electrotecniref** (company_id=3)
  en staging, y devuelve artículos con `price_source: flexxus:PRECIOVENTA1`
  (`docs/sesion-2026-10-24-deploy-flexxus.md`).
- El cliente es de Electrotecniref y las marcas que devuelve son las del taller.

La lectura consistente es que **es el ERP de Electrotecniref** y que "Suevos"
quedó como nombre en los comentarios del código. Por eso la propuesta lo
presenta como integración **de lectura contra el ERP que el cliente ya usa**,
y por eso **no se cobra aparte**: no hay costo incremental para nosotros en esa
integración y el valor es para el cliente.

**Pendiente de confirmar antes de enviar:** que el ERP de repuestos sea
efectivamente de Electrotecniref. Si fuera de un tercero, la frase "contra el
ERP de la empresa" de la propuesta sería incorrecta y habría que revisarla.

---

## 7. Pendientes

**Antes de que el cliente firme** (lo que promete el documento y el sistema
todavía no tiene):

- [ ] **Configurar el respaldo automático diario** en las dos bases y **probar
      una restauración real**, midiendo el RTO. Sin esto, el compromiso de la
      sección 6 de la propuesta no es cierto. (Requiere backend superadmin:
      hoy no hay endpoint de exportación de backups en la API de Coolify, hay
      que hacerlo por panel o por `docker exec` en el server.)
- [ ] **Implementar la exportación de datos** en formatos abiertos, o decidir
      que el dump de MySQL cumple la promesa.
- [ ] **Implementar el contador de mensajes de WhatsApp.** Con el cupo de
      400/mes incluido, el contador pasó de ser necesario para *facturar* a
      ser necesario para *cumplir* la promesa: sin él no se sabe si el
      cliente se pasó del cupo ni cuánto se le facturó (§4.1).
- [ ] **Confirmar a qué empresa pertenece el ERP Flexxus** (§6) y ajustar la
      frase de la propuesta si hace falta.

**Decisiones comerciales que pueden seguir abiertas** (no bloquean el envío,
pero conviene cerrarlas):

- [ ] **La bonificación anual** (2 meses sin cargo) es una propuesta mía, no
      un número que haya dado el usuario. Ver §3.4.
- [ ] **Preguntar si Electrotecniref tiene su propia instancia de WhatsApp.**
      Si la tiene, la factura de Meta le llega directo y el costo no pasa por
      Vogel, y el cupo de 400 ni siquiera se toca. Es la salida más limpia
      (§4.1). Está propuesto como paso 2 de la propuesta.
- [ ] **Decidir la lista de precios del catálogo de repuestos** con el cliente
      (es el paso 2 de la propuesta: lista 1 con margen, o costo).
- [ ] **Medir el costo real de la hora de soporte** (§8). Ya no bloquea: con
      300.000/mes el SLA de 4/8 h está financiado con 10–20 h/mes de margen.
- [ ] **Definir la factura electrónica**: `docs/portalvogel.md` dice que la
      facturación es una integración externa. La propuesta promete factura
      electrónica AFIP/ARCA: hay que confirmar que esa integración va a estar
      para el primer abono, o la forma de pago del mes 1 se resuelve a mano.

**Infraestructura** (para la puesta en marcha, no bloquean el envío):

- [ ] **Restaurar staging a `main`** después del merge de
      `feat/finalizacion-tecnica-cierre`.
- [ ] **Cargar el histórico en la base de producción** (hoy la producción está
      vacía) y revalidar un cierre contra el legacy.
- [ ] **Fijar la imagen de MySQL de producción** a `8.4.13` en vez de `mysql:8`.

> **Resuelto en esta revisión:** el SLA contra el precio. Con ARS 30.000/mes
> el SLA de incidente crítico en 4 h hábiles no se financiaba (1–2 h/mes de
> soporte) y había que elegir entre subir el precio, bajar el SLA o atarlo a
> los 12 meses de lanzamiento. Con **ARS 300.000/mes financia 10–20 h/mes**:
> el SLA se mantiene en toda la vigencia del contrato y la única revisión
> anual es la del IPC. El documento ya no menciona precio de lanzamiento.

---

## 8. Lo que NO se encontró verificado

Para que quede claro qué es dato medido y qué es supuesto:

| Afirmación | Estado |
|---|---|
| Volumen de OTs, usuarios, áreas, marcas | **Medido** sobre el dump |
| Liquidación y facturación mensuales | **Medido** sobre el dump, validado contra junio 2025 |
| Porcentaje del precio sobre la facturación | **Calculado** con las bases medidas |
| Ventana temporal de los promedios (9 meses completos) | **Medido**: el dump es del 21/10/2026, octubre está a medias (§3.3) |
| Banda de 1%–3% para software de gestión en SMB | **Externo**, de IDC vía fuentes secundarias ([ZENIA](https://zeniapartners.com/blog/cuanto-cuesta-un-crm-para-pymes.html), [cleverals](https://www.cleverals.com/es/precios/software-facturacion/)) |
| Tarifa de WhatsApp de Meta en Argentina | **Externo**, rate card vigente desde el 1/10/2026 ([Basework](https://www.basework.com.ar/blog/whatsapp-business-api-argentina), [wha.tools](https://wha.tools/es/whatsapp-api-pricing)) |
| Horas de soporte que financia cada abono | **Supuesto**: banda de 15.000–30.000 ARS/hora, a ajustar al costo real de la hora de Vogel |
| Tipo de cambio ARS/USD (1.550) | **Externo**, dólar oficial minorista al 26/10/2026 |
| Costo de hosting real | **No medido**: el servidor es compartido entre varios proyectos de la plataforma y el costo por tenant no está allocates |

**Sobre el supuesto de la hora:** con ARS 30.000 era el número que más faltaba
—decidía si el SLA era sostenible o no—. Con ARS 300.000 deja de ser
bloqueante: aun tomando el extremo caro de la banda (30.000 ARS/h) el abono
financia 10 horas de soporte al mes, y el SLA de 4/8 h cabe con holgura. Igual
conviene medirlo antes de mandar la propuesta, porque es el número que
permite defender el precio si el cliente pregunta.

---

## 9. Cómo reproducir las mediciones

Las cifras de §2 se sacaron del dump de staging con un parser propio que
respeta las cadenas de MySQL (los `notes` de las OTs contienen saltos de línea
y comas, así que un split ingenuo rompe las filas).

El criterio de inclusión **no es una decisión del script**: se copió del
servicio de cierre, para que el número que se publica sea el mismo que calcula
la aplicación. Por eso junio 2025 da 123 / 1.675.486,90.

```powershell
# el dump vive en backup/_work/ y está en .gitignore (16 MB con datos del cliente)
python -c "import re,collections,pathlib; ..."
```

Si los números de la propuesta se discuten, se vuelven a correr sobre el dump
y se compara contra el junio 2025 de referencia.

**Los scripts de esta sesión quedaron en `%TEMP%\docxbuild\`:**

| Script | Para qué |
|---|---|
| `precio_final.py` | Recalcula porcentajes, horas de soporte y exposición de IA/WhatsApp contra el precio final. |
| `cifras_finales.py` | Serie mensual 2026 de liquidación y facturación, con el mes incompleto marcado. Es el que produjo §3.3. |
| `recalculo_2026.py` | Lo mismo, con la validación contra junio 2025 y las dos ventanas comparadas. |
| `tabla_3_1.py` | Los porcentajes de la tabla de §3.1, calculados y no a ojo. |
| `verificar.py` | Verifica el `.docx` generado: texto real, anchos de tabla, cifras clave, ausencia de precios viejos y consistencia aritmética. |
| `propuesta.js` | El generador del documento (docx-js). |

> `verificar.py` es el control que evita mandar un documento con un número
> viejo: extrae el texto del `.docx` (no del generador), comprueba que estén
> las cifras del número final, que **no** aparezcan las de las versiones
> anteriores, y recalcula las sumas que el documento afirma (500.000 + 11 ×
> 300.000 = 3.800.000, etc.).
