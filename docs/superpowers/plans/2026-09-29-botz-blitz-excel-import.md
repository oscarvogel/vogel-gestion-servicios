# Importador Excel de trabajos de Botz Blitz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Incorporar una importación guiada del registro Excel para que un administrador revise y cargue trabajos históricos únicamente en la empresa activa.

**Architecture:** Agregar un parser XLSX aislado que lea solo las hojas detalladas previstas y entregue filas normalizadas al servicio de importación. La API obtiene siempre la empresa desde la sesión, conserva lote y procedencia para idempotencia y crea clientes/equipos/órdenes en transacción. Una vista Vue permite subir, revisar advertencias y confirmar; no se despliega ni se importan datos desde este cambio de código.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Python estándar para OOXML/XLSX, Vue 3, TypeScript y el flujo Docker/Coolify existente.

**Spec:** `docs/superpowers/specs/2026-09-29-botz-blitz-excel-import-design.md`

## Global Constraints

- El tenant de destino siempre proviene de `get_current_company_id`; la API no acepta un `company_id` elegido por el cliente.
- Solo usuarios con `work_orders.manage` pueden previsualizar o confirmar una importación.
- Leer las hojas visibles `Maquinas 2024`, `2025`, `Desarmados` y `Hoja1`; excluir resúmenes ocultos y hojas vacías.
- No inventar clientes ni fechas; las filas sin cliente o fecha válida quedan bloqueadas y no se importan.
- No usar la ficha histórica como identificador único; conservar ficha, hoja, fila y estado original.
- Una recarga del mismo archivo en la misma empresa no duplica filas importadas.
- Revisar y resolver el error actual de listado de órdenes antes de usar la pantalla como evidencia de aceptación.
- No desplegar a Coolify ni subir el Excel al entorno; el usuario revisa y despliega esta rama.

## Review Focus

- XLSX ZIP malformado, excesivamente grande o con entradas comprimidas sospechosas: rechazarlo antes de parsear y sin escribir datos (revisión manual del límite y flujo de errores del parser).
- Hoja con nombres alterados, pivotes/hojas ocultas o celdas vacías: procesar solo las cuatro hojas nombradas y omitir filas vacías (revisión de allowlist y filtros).
- Fechas Excel seriales, fechas de texto y celdas inválidas: normalizar fechas válidas con el calendario Excel y bloquear fechas inválidas (revisión de normalizador y resumen de preview).
- Nombres/teléfonos repetidos, ficha repetida o filas similares entre hojas: no colisionar clientes por ficha y exponer duplicados candidatos para decisión (revisión de comparación e idempotencia).
- Fallo durante confirmación o reintento concurrente: hacer rollback completo y mantener unicidad de procedencia por empresa (revisión de límites de transacción/índices y manejo de error).

---

### Task 1: Persistencia de lotes y procedencia importada

**Files:**
- Create: `backend/app/models/work_order_import.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260929_0013_work_order_imports.py` (`down_revision=20260927_0012`)

**Interfaces:**
- Produce modelos `WorkOrderImportBatch` (empresa, huella SHA-256 del archivo, nombre y conteo importado) y `WorkOrderImportRow` (empresa, lote, hoja, fila, ficha heredada, huella de fila y `work_order_id`).
- La unicidad de archivo y fila se acota por empresa; `work_order_id` referencia la orden creada y permite consultar procedencia.

- [ ] Definir modelos SQLAlchemy con claves foráneas, índices y restricciones únicas tenant-scoped.
- [ ] Exportar los modelos para que `backend/app/db` y Alembic los incluyan en metadata.
- [ ] Crear migración reversible siguiendo el head efectivo, sin alterar tablas de otras empresas.
- [ ] Revisar manualmente metadata, FKs y downgrade contra los modelos existentes.

### Task 2: Parser y vista previa de XLSX

**Files:**
- Create: `backend/app/services/work_order_import_parser.py`
- Create: `backend/app/services/work_order_import_service.py`

**Interfaces:**
- `parse_work_order_xlsx(content: bytes, filename: str) -> ParsedWorkbook` valida ZIP/tamaño, lee shared strings y celdas inline, y devuelve filas de las cuatro hojas permitidas con valores de origen y números de fila.
- `preview_work_order_import(db, company_id, content, filename) -> dict` normaliza cliente, contacto, equipo, fechas, estado y ficha; clasifica `ready`, `warning`, `duplicate` o `blocked` sin crear registros.

- [ ] Implementar lectura OOXML con biblioteca estándar para evitar incompatibilidad conocida del libro con pivotes; limitar tamaño comprimido/descomprimido, entradas y hojas permitidas.
- [ ] Definir normalizadores para encabezados por hoja, nombres/teléfonos, seriales de fecha Excel/texto, estado legado y campos históricos; conservar valores sin transformar necesarios para trazabilidad.
- [ ] Producir conteos y muestras por hoja, motivos de bloqueo/advertencia y candidatos de duplicado; generar hashes estables de archivo/fila.
- [ ] Revisar manualmente casos de metadatos pivote, encabezado `0` en 2025, filas sin cliente/fecha y ficha repetida, sin escribir en DB durante preview.

### Task 3: Endpoints seguros y confirmación transaccional

**Files:**
- Create: `backend/app/api/v1/work_order_imports.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/services/work_order_import_service.py`

**Interfaces:**
- `POST /work-orders/import/preview` recibe multipart `file`; devuelve `ImportPreview` usando el tenant de sesión.
- `POST /work-orders/import/confirm` recibe el token/huella del preview, selecciones explícitas de filas ambiguas y el nombre del archivo; confirma solo el lote validado para el tenant autenticado.
- Ambos endpoints requieren `work_orders.manage`; las órdenes mantienen su numeración normal y los registros de procedencia hacen idempotentes los reintentos.

- [ ] Registrar router y aplicar permisos existentes; no aceptar ni consultar `company_id` del body/query.
- [ ] Crear o resolver clientes/equipos solo dentro del `company_id` activo y crear órdenes con estado propuesto más estado original trazable.
- [ ] Confirmar en transacción: crear lote/filas/entidades, saltar filas importadas previamente y revertir todos los cambios ante fallo.
- [ ] Devolver resultado con importadas, omitidas, bloqueadas y motivos por fila; evitar registrar PII del archivo en logs.
- [ ] Revisar manualmente alcance tenant, permisos, reintentos y rollback a partir del flujo completo endpoint → servicio → repositorios/modelos.

### Task 4: Flujo de importación en Vue

**Files:**
- Create: `frontend/src/views/WorkOrderImportView.vue`
- Modify: `frontend/src/router.ts`
- Modify: `frontend/src/views/WorkOrdersView.vue`
- Modify: navegación lateral correspondiente si el acceso a Órdenes no ofrece un punto adecuado

**Interfaces:**
- Ruta autenticada `/app/work-orders/import`, bajo el permiso `work_orders.manage`; la API vuelve a aplicar este permiso en preview y confirmación.
- La vista consume los dos endpoints, muestra empresa activa, conteos/muestras por hoja y requiere confirmación explícita para enviar.

- [ ] Añadir acción “Importar trabajos” desde Órdenes y registrar ruta con guardas existentes.
- [ ] Implementar selección `.xlsx`, estados de carga/error, preview legible por hoja, corrección/selección de filas ambiguas, corrección manual de campos requeridos y omisión visible de las filas que sigan bloqueadas.
- [ ] Mostrar resultado final y vínculo a órdenes importadas; no guardar el Excel en storage permanente ni exponer identificadores de otras empresas.
- [ ] Revisar manualmente flujo visual, accesibilidad básica, respuesta ante sesión vencida y error de listado de órdenes.

### Task 5: Preparación del despliegue por el usuario

**Files:**
- Modify: documentación de importación/operación existente, si hay un lugar vigente para instrucciones de despliegue

- [ ] Documentar la migración pendiente y el recorrido: desplegar esta rama en Coolify, comprobar la versión, abrir Órdenes, previsualizar, revisar bloqueos/duplicados y confirmar en Botz Blitz.
- [ ] Revisar que Docker/Coolify aplique migraciones según el entrypoint ya existente, sin añadir credenciales ni editar `.env`.
- [ ] Entregar rama y SHA; dejar el despliegue y la carga del libro en manos del usuario.
