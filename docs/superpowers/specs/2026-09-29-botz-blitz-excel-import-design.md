# Importador de trabajos históricos de Botz Blitz

**Estado:** diseño aprobado el 2026-09-29  
**Destino de demostración:** `https://gestion-vogel.186.5.245.12.sslip.io`, empresa activa Botz Blitz  
**Origen:** `docs/Registro de ingreso de trabajos (1).xlsx`

## Objetivo

Permitir que un administrador de empresa cargue los trabajos históricos del Excel desde la interfaz, revise la interpretación de los datos y confirme la importación con trazabilidad y protección contra cargas repetidas.

## Alcance

- Incorporar una acción **Importar trabajos** en Órdenes de trabajo.
- Aceptar el libro Excel provisto y leer solo hojas con registros detallados.
- Incluir en la vista previa las hojas visibles `Maquinas 2024`, `2025`, `Desarmados` y `Hoja1`; excluir los resúmenes ocultos y las hojas vacías.
- Aplicar siempre el tenant de la sesión. El cliente no enviará un `company_id` seleccionable para la carga.
- Mostrar por hoja cuántas filas están listas, advertidas, posiblemente duplicadas o requieren corrección. La vista previa no escribirá clientes, equipos ni órdenes.
- Confirmar la carga solo después de revisar la vista previa. La operación debe conservar la hoja, fila y ficha histórica de origen, y poder reconocerse si se vuelve a subir el mismo libro.
- Restringir la función a usuarios con permiso de administrar órdenes de trabajo.
- Desplegar mediante el flujo vigente de Coolify después de revisar el cambio; importar en Botz Blitz después de comprobar la versión desplegada.

## Interpretación de datos

- Cliente: nombre y teléfono disponible.
- Equipo: tipo/categoría, marca y características/modelo.
- Orden: fecha de recepción, motivo informado, repuestos, bobinado, pago, garantía, quién recibió, técnico, sector y estado original.
- El número de orden nuevo sigue la numeración propia de la empresa. El número de ficha original se conserva como referencia histórica y no se usa como clave única.
- La aplicación propone un estado actual para cada estado legado y muestra la equivalencia antes de confirmar. Se conserva el valor legado para consulta.
- No se inventan clientes ni fechas. Las filas sin cliente o fecha válida se identifican en vista previa y deben resolverse antes de importarse.

## Duplicados e idempotencia

- No deduplicar por número de ficha solamente: ese valor se repite en el libro.
- Marcar coincidencias exactas o muy probables entre hojas para revisión; la decisión de incluir una fila ambigua queda visible antes de confirmar.
- Registrar archivo, hoja y número de fila asociado a la orden importada. Una segunda carga del mismo archivo en Botz Blitz debe detectar y omitir las filas ya importadas, sin duplicar registros.

## Criterios de aceptación

1. El flujo informa claramente que la empresa destino es Botz Blitz y no permite cambiar el tenant enviando un identificador arbitrario.
2. El Excel ofrece una vista previa por hoja, con muestras y conteos de filas válidas, advertidas, ambiguas y bloqueadas.
3. La confirmación crea clientes, equipos y órdenes bajo Botz Blitz en una transacción controlada; los datos de otras empresas no se consultan ni modifican.
4. Las filas bloqueadas no se importan silenciosamente, y el resultado informa cuántas entraron y cuáles requieren corrección.
5. La ficha original y la procedencia quedan consultables y el mismo libro no duplica órdenes al cargarse nuevamente.
6. Las órdenes importadas aparecen en el listado y el panel de Botz Blitz para la demostración.

## Fuera de alcance

- Importar los resúmenes/pivotes del Excel como órdenes.
- Adivinar fechas o crear clientes ficticios para completar campos obligatorios.
- Importar cualquier formato de Excel distinto del libro descrito sin una vista previa de mapeo.
- Desplegar automáticamente a Coolify sin revisar el commit y confirmar el destino.

## Evidencia y límites

La sesión del 2026-09-29 mostró Botz Blitz activa, 0 clientes y 0 órdenes. La lista de órdenes también mostró `No se pudieron cargar las órdenes`; ese error debe diagnosticarse antes de usar el listado como verificación final. El Excel tiene registros visibles además de hojas de resumen; sus estados y datos incompletos requieren confirmación en la vista previa.
