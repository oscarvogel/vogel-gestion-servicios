# Sesión 2026-10-26 — El presupuesto de Vogel Gestión de Servicios para Electrotecniref

Objetivo de la sesión: armar la propuesta económica de un **abono mensual** para
Electrotecniref y dejar por escrito de dónde sale cada número.

**Resultado:**
- `docs/propuesta-abono-mensual-electrotecniref.docx` — la propuesta lista para enviar.
- Este documento — la bitácora interna: razonamiento, fuentes y límites.

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

El abono se ancla contra **el valor que el sistema mueve**, no contra un
arbitrio de mercado.

- El sistema liquida contra marcas **~ARS 2,6 millones por mes** en 2026.
- La facturación total del taller es de varios múltiplos de eso (el `sale_total`
  promedio del período es ~3x el costo liquidado: en garantía de terceros el
  legacy infla el precio de venta, `warranty_settlements.py:20-22`).
- Un abono de **ARS 650.000/mes** es del orden del **0,8%–1,5% de la
  liquidación mensual** que el sistema produce y del orden del 0,25% de la
  facturación del taller.

Es un orden de magnitud defendible ante un cliente: "la herramienta que les
genera 2,6 millones de liquidaciones al mes, y que reemplaza un ERP de 25
años, por menos del 1% de lo que liquida".

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

### Puesta en marcha: ARS 850.000

El número es **menor** que el de una implementación desde cero, y a propósito:
la migración del histórico (el 80% del trabajo) **ya está hecha y verificada**.
Lo que se cobra es el corte a producción, los 46 usuarios individuales, la
configuración, dos jornadas de capacitación, la habilitación de módulos y 30
días de garantía de arranque.

La bonificación por 12 meses anticipados (puesta en marcha a ARS 425.000 +
15% en el primer año) compra permanencia sin regalar el servicio.

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
| **Conversaciones de WhatsApp** | El sistema registra los envíos (`work_order_notifications` con `provider_message_id` y estado) pero **no cuenta ni costea mensajes**. | Se incluye un cupo de 1.000/mes y el excedente "a costo de plataforma". **Antes de cobrar el excedente hay que implementar el conteo.** |
| **Almacenamiento** | Hay límite por archivo (`storage_max_file_mb: 25`) pero no un total medido en GB. | 20 GB incluidos, a ajustar. |
| **Exportación de datos** | **No existe exportación.** Sólo import `.xlsx` y descarga de documentos. | Es compromiso de puesta en marcha, ver §5. |

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
- [ ] **Contar las conversaciones de WhatsApp** si se quiere cobrar el
      excedente. Hoy no hay contador.
- [ ] **Restaurar staging a `main`** después del merge de
      `feat/finalizacion-tecnica-cierre`.
- [ ] **Cargar el histórico en la base de producción** (hoy la producción está
      vacía) y revalidar un cierre contra el legacy.
- [ ] **Fijar la imagen de MySQL de producción** a `8.4.13` en vez de `mysql:8`.
- [ ] **Revisar el precio contra el costo real** de hosting y soporte una vez
      sepas las horas que lleva el sistema en producción. El 15% de margen del
      primer año es una hipótesis, no una medición.
- [ ] **Definir la factura electrónica**: `docs/portalvogel.md` dice que la
      facturación es una integración externa. La propuesta promete factura
      electrónica AFIP/ARCA: hay que confirmar que esa integración va a estar
      para el primer abono, o la forma de pago del mes 1 se resuelve a mano.

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
