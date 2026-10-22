"""El importador de CiberBrain: las reglas que no se pueden equivocar.

Estos tests fijan las decisiones que se tomaron **midiendo** la base restaurada, no leyendo
el codigo del legacy. Si alguno falla, el importador esta tomando un camino que ya se sabe
que da un numero que no es.

Las cifras de referencia (medidas contra CiberBase el 22/10/2026) estan en el docstring de
cada test, para que si cambia un numero en la base se vea que hay que volver a medir.

Lo que NO hay aca: tests que necesiten la base real. El importador se valida corriendo el
cierre de junio 2025 contra el legacy, que cuadra centavo a centavo (123 OTs con empresa,
1.675.486,90; 91 en garantia, 1.045.148,145). Acá va lo que se puede fijar sin base: el
parseo y las reglas de mapeo.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from scripts.import_cyberbrain import mappers, source
from scripts.import_cyberbrain.steps.customers import _clave_de_agrupacion, _nombre_sin_nombre


# ---------------------------------------------------------------------------
# D2: el documento del cliente
# ---------------------------------------------------------------------------
def test_el_documento_solo_se_puebla_con_11_digitos():
    """Solo 197 de los 14.730 clientes del legacy tienen un CUIT de 11 digitos.

    El resto tiene placeholders (``100000``, ``11111111``) o nada. Con esos numeros
    guardados, el maestro de clientes queda con documentos que no son documentos.
    """
    assert mappers.cuit_de_11_digitos("20249648419") == "20249648419"
    assert mappers.cuit_de_11_digitos("20-24964841-9") == "20249648419"
    assert mappers.cuit_de_11_digitos("100000") is None
    assert mappers.cuit_de_11_digitos("11111111") is None
    assert mappers.cuit_de_11_digitos(None) is None


def test_el_cuit_se_valida_con_el_digito_verificador():
    """El digito verificador es lo que separa un CUIT de un numero con 11 digitos.

    En el legacy hay 2 CUITs de 11 digitos que no lo pasan.
    """
    assert mappers.cuit_valido("20249648419") is True
    assert mappers.cuit_valido("20249648410") is False, "digito verificador incorrecto"
    # Prefijo de tres digitos iguales: no es un CUIT real.
    assert mappers.cuit_valido("11111111112") is False
    assert mappers.cuit_valido("2024964841") is False, "10 digitos no es un CUIT"
    assert mappers.cuit_valido("2024964841X") is False


def test_un_cuit_invalido_no_llega_al_documento():
    """Si el CUIT no pasa el verificador, el documento queda en None (no un dato falso)."""
    assert mappers.cuit_normalizado("20249648419") == "20249648419"
    assert mappers.cuit_normalizado("20249648410") is None
    assert mappers.cuit_normalizado("100000") is None


def test_el_tipo_de_cliente_se_deduce_del_cuit_o_del_sufijo():
    """El legacy no tiene un campo de tipo de cliente: hay que deducirlo.

    Un CUIT valido alcanza por si solo (una persona con CUIT tambien es una empresa
    unipersonal); si no, manda el sufijo societario del nombre.
    """
    assert mappers.tipo_cliente("PEREZ JUAN", None) == "PERSON"
    assert mappers.tipo_cliente("DREAN S.A.", None) == "COMPANY"
    assert mappers.tipo_cliente("DREAN S.R.L.", None) == "COMPANY"
    assert mappers.tipo_cliente("PEREZ JUAN", "20249648419") == "COMPANY"
    # Un CUIT invalido no alcanza para decir "empresa".
    assert mappers.tipo_cliente("PEREZ JUAN", "20249648410") == "PERSON"


# ---------------------------------------------------------------------------
# D1: la clave de agrupamiento de los clientes deducidos de la OT
# ---------------------------------------------------------------------------
def test_la_clave_de_agrupamiento_normaliza_el_nombre():
    """Los 3.318 clientes deducidos de las OTs se agrupan por nombre normalizado.

    Sin normalizar, "PEREZ JUAN" y "PEREZ  JUAN " serían dos clientes distintos.
    """
    assert mappers.normalizar_nombre("  Whirlpool   Argentina  S.A. ") == "WHIRLPOOL ARGENTINA S.A."
    assert mappers.normalizar_nombre("PEREZ JUAN") == mappers.normalizar_nombre("perez juan")
    assert mappers.normalizar_nombre("") == ""
    assert mappers.normalizar_nombre(None) == ""


def test_sin_acentos_compara_nombres_que_se_veen_distintos():
    assert mappers.sin_acentos("PEREZ JUÁÑEZ") == "PEREZ JUANEZ"
    assert mappers.sin_acentos("ÁÉÍÓÚ") == "AEIOU"


# ---------------------------------------------------------------------------
# D3: no hay maestro de equipos
# ---------------------------------------------------------------------------
def test_las_series_placeholder_no_son_series():
    """El 87 % de las series del corte no son series: son "ILEGIBLE", "S/N" o "FALTA".

    Guardarlas como si fueran series llena el maestro de equipos de cosas indistinguibles.
    """
    for placeholder in ("ILEGIBLE", "FALTA", "S/N", "N/S", "SIN SERIAL", "-"):
        assert mappers.serie_util(placeholder) is None, placeholder
    assert mappers.serie_util("  22357098040280001085 ") == "22357098040280001085"
    assert mappers.serie_util("") is None
    assert mappers.serie_util(None) is None


def test_las_mesas_se_normalizan_y_las_notas_de_retirada_no_entran():
    """El legacy escribe la mesa de tres formas distintas y tambien usa el mismo campo
    para anotar retiradas de equipo.

    Los separadores se unifican en guion, asi que "TALLER - BOX B" y "BOX B" dan la misma
    mesa. Las cajas numeradas quedan con espacio ("BOX1" == "BOX 1" == "BOX-1").
    """
    assert mappers.normalizar_mesa("TALLER - BOX B") == ("BOX-B", "BOX-B")
    assert mappers.normalizar_mesa("BOX B") == ("BOX-B", "BOX-B")
    assert mappers.normalizar_mesa("BOX1") == ("BOX 1", "BOX 1")
    assert mappers.normalizar_mesa("BOX-1") == ("BOX 1", "BOX 1")
    assert mappers.normalizar_mesa("Retirada el 10/09/2022") is None
    assert mappers.normalizar_mesa("") is None


# ---------------------------------------------------------------------------
# La garantia: sale de la politica, no del flag de la OT
# ---------------------------------------------------------------------------
def test_los_tres_tipos_de_garantia_tienen_tres_estados():
    """La garantia sale de la POLITICA del area, no del flag crudo de la OT: difieren.

    Y los tres tipos del legacy (0, 1, 2) tienen que quedar en tres estados distintos: el
    2 es la garantia propia del service oficial (Alladio), que es garantia pero no de
    terceros, y no puede caer en "fuera de garantia".
    """
    assert mappers.GARANTIA_A_ESTADO == {
        0: "out_of_warranty",
        1: "warranty",
        2: "own_warranty",
    }


def test_el_estado_del_legacy_se_mapea_al_del_destino():
    """Segun dbo.CS_GetEstadoTrabajo: 4 = abierta, 7 = cerrada, 8 = liquidada."""
    assert mappers.estado_destino(8) == "Entregado"
    assert mappers.estado_destino(7) == "Listo"
    assert mappers.estado_destino(4) == "En reparación"
    assert mappers.estado_destino(0) == "En diagnóstico"
    assert mappers.estado_destino(1) == "Presupuestado"
    assert mappers.estado_destino(6) == "Anulada"
    assert mappers.estado_destino(-1) == "Recibido"


def test_una_ot_sin_estado_va_al_estado_inicial_y_no_al_final():
    """47 OTs del corte 2020+ no tienen estado en el legacy.

    Si fueran al estado final ("Entregado", que ademas es ``is_final``) se estaria
    mostrando como terminados trabajos de los que no se sabe si se terminaron.
    """
    assert mappers.estado_destino(None) == "Recibido"
    # Y un estado desconocido tambien: no se inventa un estado final.
    assert mappers.estado_destino(99) == "Recibido"


# ---------------------------------------------------------------------------
# El parseo
# ---------------------------------------------------------------------------
def test_un_null_del_legacy_es_texto_vacio():
    """El driver devuelve None y, en algunos casteos, la palabra 'NULL'."""
    assert source.texto(None) == ""
    assert source.texto("NULL") == ""
    assert source.texto("null") == ""
    assert source.texto("  PEREZ  JUAN ") == "PEREZ JUAN"


def test_los_textos_largos_se_limpian_de_saltos_y_de_barras():
    """Un texto con salto de linea rompe la pantalla; una barra rompe el formato."""
    assert source.texto("CAMBIO DE BOTONERA\r\nPUESTA EN PRUEBA") == (
        "CAMBIO DE BOTONERA PUESTA EN PRUEBA"
    )
    assert source.texto("A|B") == "A B"


def test_los_importes_se_leen_como_decimal_y_no_como_float():
    """El cierre mensual compara sumas contra el legacy: con float aparecen los centavos."""
    valor = source.decimal("1234.56")
    assert valor == Decimal("1234.56")
    assert isinstance(valor, Decimal)
    assert source.decimal(None) == Decimal("0")
    assert source.decimal("NULL") == Decimal("0")
    assert source.decimal("no es un numero") == Decimal("0")
    assert source.decimal("") == Decimal("0")


def test_la_fecha_ceros_del_legacy_es_ausencia_de_fecha():
    """El legacy usa 1900-01-01 como "sin liquidar": no es una fecha, es un vacio."""
    assert source.fecha_o_umbral(datetime(1900, 1, 1)) is None
    assert source.fecha_o_umbral(datetime(2025, 6, 18, 10, 0)) == datetime(2025, 6, 18, 10, 0)
    assert source.fecha_o_umbral(None) is None


def test_los_textos_que_no_entran_en_la_columna_se_recortan_y_se_cuentan():
    """El legacy no tiene limites de ancho y el destino si: hay que recortar y avisar.

    Los 3 telefonos de 64 caracteres que no entran en la columna de 60.
    """
    antes = source.RECORTADOS.get("customers.phone", 0)
    recortado = source.recortar("customers.phone", "9" * 64, 60)
    assert recortado is not None and len(recortado) == 60
    assert source.RECORTADOS["customers.phone"] == antes + 1
    # Un texto que entra no se cuenta.
    assert source.recortar("customers.phone", "123", 60) == "123"
    assert source.RECORTADOS["customers.phone"] == antes + 1


def test_un_texto_vacio_recortado_es_none_y_no_cadena_vacia():
    assert source.recortar("customers.phone", "", 60) is None
    assert source.recortar("customers.phone", None, 60) is None


# ---------------------------------------------------------------------------
# Los clientes sin nombre
# ---------------------------------------------------------------------------
def test_un_cliente_del_maestro_sin_nombre_recibe_un_nombre_que_lo_identifica():
    """El maestro del legacy tiene 1 cliente sin nombre (CodCli 14658).

    ``customers.name`` no puede quedar vacio: la API lo valida con ``min_length=1``, y
    un solo cliente sin nombre hace fallar el listado ENTERO de clientes con un 500.
    (Pasa: se importaba vacio y ``GET /api/v1/customers`` devolvia 500.)
    """
    fila = {"nombre": "", "codcli": "14658"}
    assert _nombre_sin_nombre("14658") == "SIN NOMBRE (CodCli 14658)"
    assert _clave_de_agrupacion(fila) == "__sin_nombre__14658"


def test_dos_clientes_del_maestro_sin_nombre_no_se_fusionan():
    """Sin la clave por CodCli, los dos clientes sin nombre del legacy serian uno solo."""
    a = {"nombre": "  ", "codcli": "14658"}
    b = {"nombre": "", "codcli": "99999"}
    assert _clave_de_agrupacion(a) != _clave_de_agrupacion(b)


def test_un_cliente_con_nombre_se_agrupa_por_nombre_normalizado():
    fila = {"nombre": "  Whirlpool   Argentina  S.A. ", "codcli": "1"}
    assert _clave_de_agrupacion(fila) == "WHIRLPOOL ARGENTINA S.A."


# ---------------------------------------------------------------------------
# Los placeholders del legacy
# ---------------------------------------------------------------------------
def test_un_placeholder_de_email_no_llega_al_cliente():
    """6.487 de los 14.730 clientes del legacy tienen "NO TIENE" (o similar) en el email.

    El destino valida el email con ``EmailStr``: copiarlo tal cual hace fallar el
    listado de clientes ENTERO con un 500. Un placeholder es la ausencia de dato.
    """
    for placeholder in ("NO TIENE", "NO SE", "NOTIENE", "TIENE", "NO", "NO TEINE", "."):
        assert mappers.email_valido(placeholder) is None, placeholder
    assert mappers.email_valido("") is None
    assert mappers.email_valido(None) is None


def test_un_email_valido_se_acepta():
    assert mappers.email_valido("carlosronaldomeyer@hotmail.com") == "carlosronaldomeyer@hotmail.com"
    assert mappers.email_valido("  info@electrotecniref.com.ar  ") == "info@electrotecniref.com.ar"
    # Si el campo trae mas de una direccion, gana la primera que sea valida.
    assert (
        mappers.email_valido("NO TIENE info@electrotecniref.com.ar")
        == "info@electrotecniref.com.ar"
    )
    assert (
        mappers.email_valido("info@electrotecniref.com.ar; otro@ejemplo.com")
        == "info@electrotecniref.com.ar"
    )


# ---------------------------------------------------------------------------
# La comision y el tipo de documento
# ---------------------------------------------------------------------------
def test_la_comision_que_no_esta_es_cero_y_no_una_comision_inventada():
    """CS_Partes.LiquidaComision: 0 = sin comision, -1 = se divide entre todos."""
    assert mappers.tipo_comision(None) == mappers.COMISION_SIN_COMISION
    assert mappers.tipo_comision(0) == mappers.COMISION_SIN_COMISION
    assert mappers.tipo_comision(-1) == mappers.COMISION_TODOS
    assert mappers.tipo_comision(-2) == mappers.COMISION_RESPONSABLE
    assert mappers.tipo_comision(42) == 42


def test_el_estado_de_factura_desconocido_es_una_factura():
    assert mappers.tipo_invoice(None) == "factura"
    assert mappers.tipo_invoice(1) == "factura"
