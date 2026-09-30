# Importación de trabajos históricos

El importador de órdenes de trabajo procesa archivos `.xlsx` de hasta 15 MB. Lee las hojas detalladas `Maquinas 2024`, `2025`, `Desarmados` y `Hoja1`; ignora hojas ocultas y resúmenes.

## Despliegue y carga

1. Revisá la rama y el commit antes de seleccionarlos en Coolify. El contenedor de backend aplica `alembic upgrade head` al iniciar, incluida la migración de procedencia de importación.
2. Desplegá el commit aprobado en el recurso Coolify correspondiente. No se debe ejecutar el importador antes de que el frontend y backend muestren esa versión.
3. Ingresá a la empresa de destino y abrí **Órdenes de trabajo → Importar trabajos**. El servidor toma la empresa activa de la sesión y exige `work_orders.manage`.
4. Seleccioná el Excel y generá la vista previa. Revisá los conteos de cada hoja, los bloqueos y la equivalencia de estados. Completá cliente, fecha o categoría en las filas bloqueadas cuando el libro no los tenga; marcá las coincidencias ambiguas solo si son trabajos distintos.
5. Confirmá la importación. Los cambios se guardan en una transacción; ante un error se revierten juntos. El resultado informa órdenes creadas, filas omitidas y filas que aún requieren corrección.
6. Abrí la lista de órdenes y revisá una orden importada. La nota y el registro de procedencia conservan hoja, fila, ficha y campos originales.

Subir otra vez el mismo libro a la misma empresa omite las filas ya importadas usando la huella del archivo y la ubicación hoja/fila. La ficha histórica no se usa como identificador único.