# Sesión 2026-10-26 — El presupuesto de Vogel Gestión de Servicios para Electrotecniref

Objetivo de la sesión: armar la propuesta económica de un **abono mensual** para
Electrotecniref y dejar por escrito de dónde sale cada número.

**Resultado:**
- `docs/propuesta-abono-mensual-electrotecniref.docx` — la propuesta lista para enviar.
- Este documento — la bitácora interna: razonamiento, fuentes y límites.

**Números finales:**

| Concepto | Importe |
|---|---:|
| Puesta en marcha (única vez) | **ARS 500.000** |
| Abono mensual base | **ARS 30.000 / mes** |
| Precio de lista del abono (a partir del mes 13) | ARS 120.000 / mes |
| Cuota de IA incluida | USD 10 / mes |

> La primera versión de esta sesión propuso ARS 650.000/mes y ARS 850.000 de
> puesta en marcha. **El precio mensual estaba mal calculado** (§3.1) y se
> corrigió. Los números de arriba son los que van firmados.

---

## 1. La decisión de encuadre

La pregunta era "cómo plantear un abono mensual". Lo que se decidió:

| Decisión | Elección | Por qué |
|---|---|---|
| Moneda del abono base | **ARS, con ajuste por IPC anual** | El hosting y el soporte se pagan en pesos. Fijar el abono en una moneda dura congela el margen contra la inflación local. |
| Moneda de los adicionales | **USD** | El costo real de la IA está medido en dólares y se factura aparte. |
| Unidad de cobro | **Por empresa (tenant)** | El sistema ya es multiempresa y el tenant es el que activa módulos. No se cobra por usuario: obligaría a auditar licencias y castiga al cliente que activa gente. |
| Puesta en marcha | **Única vez, por separado** | Es trabajo real y por una sola vez, no un abono recurrente. Mezclarla en el mensual le hace ruido al cliente. |

**Lo que NO se hizo, y por qué:** un precio por usuario o por orden de trabajo.
El volumen real ya está medido y es estable (ver §2), así que un abono por
tenant con límites de volumen ancho y un excedente medido cubre el caso sin
meter un mecanismo de medición que el sistema no tiene hoy.

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

- Mediana mensual: **114 OTs**. Promedio 2025-2026: **128**. Pico: **181** (julio 2025).
- Total del legacy: **56.619 trabajos** en 25 años (`docs/informe-migracion-ciberbrain.md`).

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
| **Promedio mensual 2026** | **ARS 2.631.921** |

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
> de la liquidación mensual". **Eso estaba mal: es 24,9%.** El error fue mío
> (dividí mal al mezclar la base de cálculo). El precio se recalculó contra
> las dos bases correctas y se corrigió la propuesta. Ver §3.1.

El abono se ancla contra **el valor que el sistema mueve**, no contra un
arbitrio de mercado. Y hay **dos** bases posibles, y no dan lo mismo:

| Base | Promedio mensual 2026 | Qué es |
|---|---:|---|
| **Liquidación a marcas** (`cost_total` de las OTs con empresa a liquidar) | **ARS 2.610.309** | Lo que las marcas le pagan al taller. Es lo que el sistema *produce*. |
| **Facturación del taller** (`sale_total` de todas las OTs) | **ARS 9.519.548** | Lo que el taller le factura a sus clientes. Incluye el trabajo fuera de garantía. |

Anualizado, el taller factura ~**ARS 114 millones por año** (2026).

### 3.1 El precio como porcentaje de cada base

| Abono mensual | % de la liquidación | % de la facturación | Horas de soporte que financia* |
|---|---:|---:|---:|
| ARS 30.000 | 1,15% | **0,32%** | 1 a 2 h/mes |
| ARS 120.000 | 4,60% | 1,26% | 4 a 8 h/mes |
| ARS 200.000 | 7,66% | 2,10% | 6,7 a 13,3 h/mes |
| ARS 650.000 | 24,90% | 6,83% | 21,7 a 43,3 h/mes |

\* A 15.000–30.000 ARS/hora. Es un supuesto, no un dato del repo: hay que
ajustarlo al costo real de la hora de Vogel.

**La lectura honesta:** contra la facturación del taller, el software de
gestión en una pyme de servicios se ubica en el **1%–3%** (IDC, vía
ZENIA/cleverals). ARS 120.000–200.000 cae en esa banda. ARS 650.000 la
supera por más del doble; ARS 30.000 queda por debajo del piso.

### 3.2 El número que deja el error

El primer error de la bitácora (la base mal calculada) fue el que llevó a
proponer ARS 650.000. Recalculado contra las bases correctas, **el mismo
ancla que yo había anunciado —0,8%–1,5% de la liquidación— da
aproximadamente ARS 30.000**, no ARS 650.000. El número que propuso el
usuario es el que sale de la regla que la propia bitácora enunciaba.

Es un recordatorio de por qué las cifras de acá se miden y no se estiman: un
porcentaje mal calculado se ve igual de convincente que uno bien calculado.


### Los límites incluidos

Calibrados con margen sobre el uso real, porque el excedente **debe ser la
excepción**:

| Concepto | Incluido | Uso real | Excedente |
|---|---:|---:|---:|
| Usuarios activos | 75 | 46 | ARS 4.000/usuario/mes |
| OTs por mes | 250 | 128 (pico 181) | ARS 1.200/OT |
| Áreas de trabajo | 150 | 126 | sin costo |
| Empresas a liquidar | sin límite | 34 | — |

Las áreas van 126 de 150 porque **es el número que ya está cargado** y no va a
crecer: son las marcas con las que se trabaja. Subir ese límite no genera
conversaciones comerciales.

### Puesta en marcha: ARS 500.000

El número es **menor** que el de una implementación desde cero, y a propósito:
la migración del histórico (el 80% del trabajo) **ya está hecha y verificada**.
Lo que se cobra es el corte a producción, los 46 usuarios individuales, la
configuración, dos jornadas de capacitación, la habilitación de módulos y 30
días de garantía de arranque.

### El abono mensual: ARS 30.000

Recalculado contra las bases correctas (§3.1), el ancla que la propia bitácora
enunciaba —0,8%–1,5% de la liquidación— da este número. Contra la
facturación del taller es 0,32%, por debajo del piso del 1% del benchmark.

Es un precio de **entrada deliberado**: entra un cliente de referencia con
migración ya hecha, a cambio de que la operación arranque y haya un caso real
en producción. El riesgo de un abono tan bajo es que **no financia el
soporte**: 1 a 2 horas de soporte al mes, y un solo incidente de 3 horas
consume el presupuesto completo del mes. Por eso el documento tiene que
cambiar en dos puntos (ver §4.1): el alcance del soporte y el cupo de IA.

### Lo que hay que ajustar si el abono queda en 30.000

| Punto | Ajustar | Por qué |
|---|---|---|
| Cuota de IA | De USD 30 a **USD 10** incluidos | A 1.550 el dólar, USD 30 son ~ARS 46.500: más que el abono entero. El uso real del taller es de céntimos (100 turnos = USD 0,33), así que USD 10 sigue siendo 30x el uso esperado. |
| Alcance del soporte | **Sin SLA de 4/8 horas** en el abono base | 1–2 h/mes no cubren un SLA de incidente crítico en 4 h hábiles. O el SLA sube de precio, o el abono sube. |
| WhatsApp | **No incluido**; se factura a consumo real | Ver §4.1: a la tarifa de Meta vigente, 2 avisos por OT son ~ARS 8.600/mes, el 29% del abono. |
| Precio de lista vs. precio de entrada | Publicar **ARS 120.000** como precio de lista, con **ARS 30.000** como precio de lanzamiento hasta el mes 12 | Un cliente que entra con un precio de lista bajo no puede renegociar a la baja, y a los 12 meses no hay margen para el ajuste por IPC. |

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

Es decir: **la mitad de la propuesta comercial ya está instrumentada en el
código**. La cuota de IA por empresa con medición mensual y control de
plataforma es exactamente el mecanismo de un abono por consumo.

### Lo que NO se puede medir hoy, y por eso no se factura así

| Concepto | Estado real | Decisión |
|---|---|---|
| **Conversaciones de WhatsApp** | El sistema registra los envíos (`work_order_notifications` con `provider_message_id` y estado) pero **no cuenta ni costea mensajes**. | **No se incluye un cupo de 1.000/mes.** Ver §4.1: a la tarifa de Meta vigente, ese cupo son ~ARS 37.680/mes. Se factura a consumo real. **Antes hay que implementar el conteo.** |
| **Almacenamiento** | Hay límite por archivo (`storage_max_file_mb: 25`) pero no un total medido en GB. | 20 GB incluidos, a ajustar. |
| **Exportación de datos** | **No existe exportación.** Sólo import `.xlsx` y descarga de documentos. | Es compromiso de puesta en marcha, ver §5. |

### 4.1 El costo de WhatsApp, que es el que rompe un abono de 30.000

Meta factura **por mensaje entregado**, no por conversación, y su rate card
para Argentina (vigente desde el 1/10/2026) es:

| Categoría | Precio | Nota |
|---|---:|---|
| Servicio (responde a un cliente que te escribió, dentro de 24 h) | **ARS 37,68** | Las primeras 1.000 respuestas al mes por número son gratis |
| Utilidad (aviso de estado de una OT) | **ARS 37,68** | **Siempre se cobra**, también dentro de una ventana de servicio abierta |
| Marketing | ARS 89,56 | — |

Un aviso de estado de OT es categoría **utilidad**: se cobra siempre.

El taller tiene 114 OTs/mes. Con 2 avisos por OT (recepción y entrega) son
228 mensajes/mes:

```
228 mensajes × ARS 37,68 = ARS 8.591/mes
```

**Eso es el 29% de un abono de ARS 30.000**, y el sistema **no cuenta los
mensajes**: no hay forma de saber hoy cuánto se gastó.

Por eso la primera versión de la propuesta (1.000 conversaciones/mes
incluidas) era un pasivo de hasta **ARS 37.680/mes** — más que el abono
entero. Con un abono de 30.000, WhatsApp **tiene que salir del incluido** y
facturarse a consumo real, con el contador implementado primero.

La salida más limpia: que Electrotecniref use **su propia instancia** de
WhatsApp (el sistema ya lo soporta: `whatsapp_api_key_encrypted` por empresa,
con `whatsapp_use_platform_key` como opt-in a la key de plataforma). Si el
taller tiene su número, la factura de Meta le llega a él y a Vogel no le
entra ese costo por el medio.

---

## 5. Lo que se promete y lo que hay que hacer antes de firmar

Esta es la parte que importa: **la propuesta promete dos cosas que el sistema
todavía no tiene.** Hay que cerrarlas antes de que el cliente las firme como
compromiso.

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
| Asistente con IA | Apagado | Apagado | Se habilita por plataforma con `PUT /companies/{id}/ai` + cuota. Ya está instrumentado. |
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

- [ ] **Configurar el respaldo automático diario** en las dos bases y **probar
      una restauración real**, midiendo el RTO. Sin esto, el compromiso de la
      sección 6 de la propuesta no es cierto. (Requiere backend superadmin:
      hoy no hay endpoint de exportación de backups en la API de Coolify, hay
      que hacerlo por panel o por `docker exec` en el server.)
- [ ] **Implementar la exportación de datos** en formatos abiertos, o decidir
      que el dump de MySQL cumple la promesa.
- [ ] **Confirmar a qué empresa pertenece el ERP Flexxus** (§6) y ajustar la
      frase de la propuesta si hace falta.
- [ ] **Decidir la lista de precios del catálogo de repuestos** con el cliente
      (es el paso 2 de la propuesta: lista 1 con margen, o costo).
- [ ] **Contar los mensajes de WhatsApp** antes de facturar el consumo. Hoy
      no hay contador, y con el cupo incluido eliminado el gasto se vuelve
      una cifra que el cliente va a pedir ver.
- [ ] **Preguntar si Electrotecniref tiene su propia instancia de WhatsApp.**
      Si la tiene, la factura de Meta le llega directo y el costo no pasa por
      Vogel. Es la salida más limpia (§4.1).
- [ ] **Revisar el SLA contra el precio.** Con ARS 30.000/mes el SLA de
      incidente crítico en 4 h hábiles financia 1–2 horas de soporte al mes.
      Hay que decidir: sube el precio, baja el SLA, o el SLA de los 12 meses
      de lanzamiento se acepta como un esfuerzo razonable y se revisa al mes 13.
- [ ] **Restaurar staging a `main`** después del merge de
      `feat/finalizacion-tecnica-cierre`.
- [ ] **Cargar el histórico en la base de producción** (hoy la producción está
      vacía) y revalidar un cierre contra el legacy.
- [ ] **Fijar la imagen de MySQL de producción** a `8.4.13` en vez de `mysql:8`.
- [ ] **Definir la factura electrónica**: `docs/portalvogel.md` dice que la
      facturación es una integración externa. La propuesta promete factura
      electrónica AFIP/ARCA: hay que confirmar que esa integración va a estar
      para el primer abono, o la forma de pago del mes 1 se resuelve a mano.

---

## 8. Lo que NO se encontró verificado

Para que quede claro qué es dato medido y qué es supuesto:

| Afirmación | Estado |
|---|---|
| Volumen de OTs, usuarios, áreas, marcas | **Medido** sobre el dump |
| Liquidación y facturación mensuales | **Medido** sobre el dump, validado contra junio 2025 |
| Porcentaje del precio sobre la facturación | **Calculado** con las bases medidas |
| Banda de 1%–3% para software de gestión en SMB | **Externo**, de IDC vía fuentes secundarias ([ZENIA](https://zeniapartners.com/blog/cuanto-cuesta-un-crm-para-pymes.html), [cleverals](https://www.cleverals.com/es/precios/software-facturacion/)) |
| Tarifa de WhatsApp de Meta en Argentina | **Externo**, rate card vigente desde el 1/10/2026 ([Basework](https://www.basework.com.ar/blog/whatsapp-business-api-argentina), [wha.tools](https://wha.tools/es/whatsapp-api-pricing)) |
| Horas de soporte que financia cada abono | **Supuesto**: banda de 15.000–30.000 ARS/hora, a ajustar al costo real de la hora de Vogel |
| Tipo de cambio ARS/USD (1.550) | **Externo**, dólar oficial minorista al 26/10/2026 |
| Costo de hosting real | **No medido**: el servidor es compartido entre varios proyectos de la plataforma y el costo por tenant no está allocates |

**Sobre el supuesto de la hora:** es el número que más falta. Con él se decide
si ARS 30.000 financia o no el soporte, y por lo tanto si el SLA de la
propuesta es sustainable. Conviene calcularlo antes de mandar la propuesta.


---

## 8. Cómo reproducir las mediciones

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
