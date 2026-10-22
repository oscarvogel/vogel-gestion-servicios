#!/bin/bash
# Vuelca la definicion de los objetos de programacion relevantes y el esquema de
# las tablas clave que faltan.
set -u
SA_PWD='Cb#Miercoles2026!x9'
CONTAINER='cb-sql'
OUT=/home/oscar/cb_restore/out
mkdir -p "$OUT/procs"

q() {
  docker exec "$CONTAINER" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PWD" -d CiberBase -C -y 0 -s '|' -Q "$1"
}

# --- Definiciones de procedimientos y funciones ---
# Cada definicion se escribe en su propio archivo para poder leerlas de a una.
NAMES="CC_ComisionesTrabajos
CC_ComisionesVentas
CC_ComisionesxEsquema
CC_EsquemaComisionVenta
CC_ObtenerComisionaFecha
CS_PorcentajeEscalaComision
CS_ImporteALiquidarOrden
CC_TraerUsuariosComisiones
CS_ListaUsuariosComision
CP_PartesLiquidacionTecnico
CC_OrdenarComisionxUsuario
CK_UbicacionPreferida
CK_OrdenUbicacionPreferida
CS_ObtenerDescripcionUbicacion
CS_ObtenerTipoUbicacion
CS_GetUbicacionAnterior
CK_GetUbicacionesIngreso
CK_GetUbicacionesEgreso
AUX_GenerarLogUbicaciones
CS_GetEstadoTrabajo
CS_SaldoTrabajo
CS_ObtenerTipoUbicacion
CS_ObtenerReparacionesTrabajo
CS_ObtenerConsumosTrabajo
CS_CodCliTrabajo
CK_CantidadUbicacion
CS_ServicioTrabajo
CG_ObtenerDatoTrabajoDesdeItemRemito
CG_Generar_Factura
CG_ItemsFacturaARemitir
CS_ControlStockTecnico
CK_StockArticuloxTecnico
CC_ObtenerDatosImpFacturacion
CG_ObtenerItemsImpresionFactura"

for name in $NAMES; do
  q "SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.$name'));" > "$OUT/procs/$name.sql" 2>&1
done

echo "--- procedimientos volcados ---"
ls -la $OUT/procs | awk '{print $5, $9}'
echo "PROCS_DONE"
