# Documentos de equipo (#43)

**Estado:** en curso, 2026-10-02
**Rama:** `feat/issue-43-documentos-equipo`

## Objetivo

Que cada equipo conserve su propio archivo documental e histórico, con fotos, videos,
audios, PDFs y lo que se permita por configuración, sin meter los binarios en MySQL.

## Decisión de almacenamiento: volumen + sistema de archivos

Se implementa una **interfaz de storage** con dos implementaciones, elegibles por
configuración:

- **Filesystem local** (default) — un volumen persistente en el contenedor. Es lo mismo
  que ya hace la gateway de WhatsApp con la multimedia inbound
  (`/app/data/media-storage/<instanceId>/`): no depende de ningún servicio externo y es
  lo más simple de operar en un servidor único.
- **S3-compatible** — para cuando haya bucket. Se agrega implementando la interfaz y
  cambiando variables de entorno.

**El dominio no conoce ninguna de las dos.** El issue lo pide explícitamente: *"la
implementación debe permitir cambiar proveedor/backend sin acoplar el dominio del equipo a
un proveedor concreto"*.

Ojo con la pantalla de S3 Storage de Coolify: es **otra cosa**. Es el destino donde Coolify
manda los backups de las bases, y está vacío. Sirve para no perder los datos si se cae el
disco, pero no es almacenamiento de aplicación. Pueden convivir con prefijos distintos en
el mismo bucket, pero la integración de los documentos es nuestra.

## Modelo

`equipment_documents`, tenant-scoped, con los binarios afuera:

- `id`, `company_id`, `equipment_id`
- `work_order_id` **nullable**: el archivo pertenece al historial del equipo y
  opcionalmente a una OT. Los que cuelgan de una OT siguen siendo visibles desde el equipo.
- `original_filename`, `mime_type`, `size_bytes`, `storage_key`
- `description` (nota del que lo sube)
- `uploaded_by_user_id`, `created_at`
- `deleted_at` + `deleted_by_user_id`: **borrado lógico**, no se borra el archivo de una.

**No hay lista rígida de extensiones.** El issue lo pide así: se guarda el MIME, el nombre
original, el tamaño y los metadatos, y la configuración decide qué se admite.

### El `storage_key` se genera en el servidor

Nunca se usa el nombre que manda el frontend. Se compone con `company_id`, equipo y un
identificador aleatorio. Un nombre de archivo es del usuario y no puede ser una clave:
`../../etc/passwd`, espacios, acentos, todo es problema. El nombre original va en su
columna, que es solo informational.

### URLs protegidas

La descarga **no** expone el archivo: pasa por un endpoint que valida sesión, permiso y
tenant, y sirve el contenido. Servir el archivo directamente desde el disco publicaría
objetos privados. Para integraciones externas (mandar el archivo a WhatsApp) se puede
generar una URL prefirmada de corta duración.

## Permisos

Reutilizo los que ya existen en vez de inventar un namespace nuevo:

- `equipment.view` — listar y descargar
- `equipment.manage` — subir, editar la descripción y dar de baja

## Auditoría

La tabla es en sí misma el registro: quién lo subió, cuándo, de qué equipo, a qué OT,
cuándo se dio de baja y por qué. Los eventos de baja van también a `work_order_events`
cuando hay OT asociada, que es el historial que el usuario ya mira desde la OT.

## Reglas de aislamiento

- `company_id` sale del tenant de la sesión, **nunca del frontend**.
- Antes de tocar un archivo se valida que el equipo, la OT y el documento pertenezcan a la
  empresa activa. Un `document_id` de otra empresa responde 404, no 403: no se le confirma
  la existencia.

## Fuera de alcance

- **Envío del documento al cliente por WhatsApp**: la gateway ya lo soporta
  (`POST /instances/:id/media`), pero es un PR aparte sobre lo ya construido acá.
- Búsqueda y filtros avanzados: se deja la lista paginada del equipo.
- Análisis con IA, transcripción de audio y resumen de PDF: el issue los menciona como
  preparación futura.
